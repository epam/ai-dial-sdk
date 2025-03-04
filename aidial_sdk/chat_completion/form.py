from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
    get_args,
)

from pydantic import BaseModel
from pydantic.v1.validators import make_literal_validator

from aidial_sdk.pydantic import PYDANTIC_V2

if TYPE_CHECKING:
    from pydantic import field_validator as validator
    from pydantic._internal._model_construction import ModelMetaclass
    from pydantic.fields import FieldInfo
else:
    if PYDANTIC_V2:
        from pydantic import field_validator as validator
        from pydantic._internal._model_construction import ModelMetaclass
        from pydantic.fields import FieldInfo
    else:
        from pydantic import validator
        from pydantic.main import ModelMetaclass
        from pydantic.v1.fields import FieldInfo

_T = TypeVar("_T")


class _ConfigWrapper(ABC):
    @abstractmethod
    def set_field(self, field: str, value: Any) -> None:
        pass

    @abstractmethod
    def get_field(self, field: str, default: Any) -> Any:
        pass

    @abstractmethod
    def to_dict(self) -> dict:
        pass


class _ConfigV1(_ConfigWrapper):
    config_cls: type

    def __init__(self, config_cls: type):
        self.config_cls = config_cls

    def set_field(self, field: str, value: Any) -> None:
        setattr(self.config_cls, field, value)

    def get_field(self, field: str, default: Any) -> Any:
        return getattr(self.config_cls, field, default)

    def to_dict(self) -> dict:
        return dict(self.config_cls.__dict__)


class _ConfigV2(_ConfigWrapper):
    model_config: dict

    def __init__(self, model_config: dict):
        self.model_config = model_config

    def set_field(self, field: str, value: Any) -> None:
        self.model_config[field] = value

    def get_field(self, field: str, default: Any) -> Any:
        return self.model_config.get(field, default)

    def to_dict(self) -> dict:
        return self.model_config


def _get_model_config(namespace: Dict[str, Any]) -> _ConfigWrapper:
    if PYDANTIC_V2:
        model_config = namespace["model_config"] = (
            namespace.get("model_config") or {}
        )
        return _ConfigV2(model_config)
    else:
        if (config_cls := namespace.get("Config")) is None:
            config_cls = type("Config", (object,), {})

            if module := namespace.get("__module__"):
                config_cls.__module__ = module
            if qualname := namespace.get("__qualname__"):
                config_cls.__qualname__ = f"{qualname}.{config_cls.__name__}"

            namespace["Config"] = config_cls

        return _ConfigV1(config_cls)


@dataclass
class Button(Generic[_T]):
    const: _T
    title: str
    confirmationMessage: Optional[str] = None
    populateText: Optional[str] = None
    submit: bool = False

    def schema(self) -> dict:
        return {
            "const": self.const,
            "title": self.title,
            "dial:widgetOptions": {
                "confirmationMessage": self.confirmationMessage,
                "populateText": self.populateText,
                "submit": self.submit,
            },
        }


def _extract_buttons_field(field_info: Any) -> Any:
    if not isinstance(field_info, FieldInfo):
        return None

    if PYDANTIC_V2:
        extra = field_info.json_schema_extra
        if not isinstance(extra, dict):
            return None
        return extra.get("buttons")
    else:
        return field_info.extra.get("buttons")  # type: ignore


class FormMetaclass(ModelMetaclass):
    def __new__(
        mcs,  # pyright: ignore[reportSelfClsParameterName]
        name,
        bases,
        namespace: dict,
        **kwargs,
    ):
        # Inject buttons validators

        validators = {}
        button_fields: Dict[str, List[Button]] = {}

        for field_name, field_info in namespace.items():
            if (buttons_extra := _extract_buttons_field(field_info)) is None:
                continue

            buttons = _get_buttons(f"{name}.{field_name}", buttons_extra)
            if not buttons:
                continue

            button_fields[field_name] = buttons

            consts = tuple(button.const for button in buttons)
            literal_type = Literal[consts]
            literal_validator = make_literal_validator(literal_type)

            def _make_check_value(literal_validator):
                if PYDANTIC_V2:

                    def check_value_v2(value, *args, **kwargs):
                        return literal_validator(value)

                    return check_value_v2
                else:

                    def check_value_v1(value, values, config, field):
                        return literal_validator(value)

                    return check_value_v1

            extra_opts = {} if PYDANTIC_V2 else {"allow_reuse": True}
            validators[f"_validate_{field_name}"] = validator(
                field_name, **extra_opts  # type: ignore
            )(_make_check_value(literal_validator))

        namespace.update(validators)

        # Inject schema post processing

        model_config = _get_model_config(namespace)

        model_config.set_field("extra", "forbid")

        attr_name = "json_schema_extra" if PYDANTIC_V2 else "schema_extra"
        old_schema_extra = model_config.get_field(attr_name, None)

        def new_schema_extra(
            schema: Dict[str, Any], model: Type[BaseModel]
        ) -> None:
            if old_schema_extra:
                old_schema_extra(schema, model)

            _handle_config_extensions(model_config.to_dict(), schema)
            _handle_buttons_extension(name, schema, button_fields)

        model_config.set_field(attr_name, staticmethod(new_schema_extra))

        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        return cls


def _handle_config_extensions(config: dict, schema: Dict[str, Any]) -> None:
    if (disable_input := config.get("chat_message_input_disabled")) is not None:
        schema["dial:chatMessageInputDisabled"] = disable_input is True


def _handle_buttons_extension(
    cls_name: str,
    schema: Dict[str, Any],
    button_fields: Dict[str, List[Button]],
) -> None:
    for field_name, buttons in button_fields.items():
        prop = schema["properties"][field_name]
        prop.pop("buttons", None)

        button_schemas = [button.schema() for button in buttons]

        prop["dial:widget"] = "buttons"
        prop["oneOf"] = button_schemas

        if (anyOf := prop.pop("anyOf", None)) is not None:
            # Optional types are translated in Pydantic V2 to
            # {'anyOf': [{'type': 'integer'}, {'type': 'null'}], 'default': null}
            # that conflicts with the follow-up 'oneOf' definition.
            types = {subschema["type"] for subschema in anyOf}
            types.discard("null")
            if len(types) != 1:
                raise ValueError(
                    f"Field {field_name} has conflicting types {types}."
                )
            prop.pop("default", None)
            prop["type"] = types.pop()

        # NOTE: The meta schema of the DIAL forms only supports
        # 'number' type, so we convert 'integer' to 'number'.
        # Could be removed once this restriction is lifted.
        if prop["type"] == "integer":
            prop["type"] = "number"

        # NOTE: The meta schema of the DIAL forms only supports 'number' type.
        # Could be removed once this restriction is lifted.
        if prop["type"] != "number":
            raise ValueError(
                f"Button value must be a number. However, field {cls_name}.{field_name} has type {prop['type']!r}."
            )


_Model = TypeVar("_Model", bound=BaseModel)


def form(
    *,
    chat_message_input_disabled: Optional[bool] = None,
    **kwargs: Dict[str, Union[FieldInfo, Any]],
) -> Callable[[Type[_Model]], Type[_Model]]:
    def _create_class(cls: Type[_Model]) -> Type[_Model]:
        namespace: Dict[str, Any] = {
            "__module__": cls.__module__,
            "__qualname__": cls.__qualname__,
        }

        annotations: Dict[str, Any] = {}

        # Injecting config extensions
        if chat_message_input_disabled is not None:
            conf_fields = {
                "chat_message_input_disabled": chat_message_input_disabled
            }
            if PYDANTIC_V2:
                namespace["model_config"] = conf_fields
            else:
                conf_base_cls = getattr(cls, "Config", object)
                config_cls = type("Config", (conf_base_cls,), conf_fields)
                config_cls.__module__ = cls.__module__
                config_cls.__qualname__ = f"{cls.__qualname__}.Config"
                namespace["Config"] = config_cls

        # Injecting button extensions
        for name, field_info in kwargs.items():
            field_name = f"{cls.__name__}.{name}"

            if (buttons_extra := _extract_buttons_field(field_info)) is None:
                raise ValueError(
                    f"Field descriptor of {field_name} is missing 'buttons' parameter."
                )

            buttons = _get_buttons(field_name, buttons_extra)

            namespace[name] = field_info

            button_type = type(buttons[0].const)
            if field_type := cls.__annotations__.get(name):
                annotations[name] = field_type
                field_type_base = _get_base_type(field_type)
                if field_type_base != button_type:
                    raise ValueError(
                        f"Field {field_name} has type {field_type_base} "
                        f"but buttons are of type {button_type}."
                    )
            else:
                annotations[name] = button_type

        if annotations:
            namespace["__annotations__"] = annotations

        cls_name = f"_{cls.__name__}"
        return FormMetaclass(cls_name, (cls,), namespace)  # type: ignore

    return _create_class


def _get_base_type(tp: Type[_T]) -> Type[_T]:
    """Returns T if given Optional[T], otherwise returns the type unchanged."""
    args = get_args(tp)
    if len(args) == 2 and type(None) in args:
        return next(arg for arg in args if arg is not type(None))
    return tp


def _get_buttons(field_name: str, buttons: Any) -> List[Button]:
    if not isinstance(buttons, list):
        raise ValueError(
            f"'buttons' parameter of the field descriptor for {field_name} must be a list, but got {type(buttons).__name__}."
        )

    if not all(isinstance(button, Button) for button in buttons):
        raise ValueError(
            f"'buttons' parameter of the field descriptor for {field_name} must be a list of Button objects."
        )

    return buttons
