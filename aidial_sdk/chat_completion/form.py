from dataclasses import dataclass
from typing import (
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

from pydantic.v1.fields import FieldInfo
from pydantic.v1.validators import make_literal_validator

from aidial_sdk.pydantic_v1 import BaseModel, ModelMetaclass, validator

_T = TypeVar("_T")


_SUPPORTED_BUTTON_TYPES = ["number", "integer", "boolean", "string"]


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


class FormMetaclass(ModelMetaclass):
    def __new__(mcs, name, bases, namespace: dict, **kwargs):
        # Inject buttons validators

        validators = {}
        for field_name, field_info in namespace.items():
            if not isinstance(field_info, FieldInfo):
                continue

            buttons_extra = field_info.extra.get("buttons")
            if not buttons_extra:
                continue

            buttons = _get_buttons(f"{name}.{field_name}", buttons_extra)

            consts = tuple(button.const for button in buttons)
            literal_type = Literal[consts]
            literal_validator = make_literal_validator(literal_type)

            def _make_check_value(literal_validator):
                def check_value(value, values, config, field):
                    return literal_validator(value)

                return check_value

            validators[f"_validate_{field_name}"] = validator(
                field_name, allow_reuse=True
            )(_make_check_value(literal_validator))

        namespace.update(validators)

        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Inject schema post processing

        if (config := getattr(cls, "Config", None)) is None:

            class Config:
                pass

            config = cls.Config = Config

        config.extra = "forbid"  # type: ignore

        old_schema_extra = getattr(config, "schema_extra", None)

        def new_schema_extra(
            schema: Dict[str, Any], model: Type[BaseModel]
        ) -> None:
            if old_schema_extra:
                old_schema_extra(schema, model)

            _handle_config_extensions(config, schema)
            _handle_buttons_extension(schema)

        config.schema_extra = staticmethod(new_schema_extra)  # type: ignore

        return cls


def _handle_config_extensions(config: Any, schema: Dict[str, Any]) -> None:
    if (
        disable_input := getattr(config, "chat_message_input_disabled", None)
    ) is not None:
        schema["dial:chatMessageInputDisabled"] = disable_input is True


def _handle_buttons_extension(schema: Dict[str, Any]) -> None:
    for prop_name, prop in schema.get("properties", {}).items():
        if buttons := prop.pop("buttons", None):
            button_schemas: List[dict] = []
            for button in buttons:
                assert isinstance(button, Button)
                button_schemas.append(button.schema())
            prop["dial:widget"] = "buttons"
            prop["oneOf"] = button_schemas

            if prop["type"] not in _SUPPORTED_BUTTON_TYPES:
                ts = ", ".join(f"{ty!r}" for ty in _SUPPORTED_BUTTON_TYPES)
                raise ValueError(
                    f"Button value must be a one of the following types: {ts}. "
                    f"However, field {schema['title']}.{prop_name} has type {prop['type']!r}."
                )


_Model = TypeVar("_Model", bound=BaseModel)


def form(
    *,
    chat_message_input_disabled: Optional[bool] = None,
    **kwargs: Dict[str, Union[FieldInfo, Any]],
) -> Callable[[Type[_Model]], Type[_Model]]:
    def _create_class(cls: Type[_Model]) -> Type[_Model]:
        namespace: Dict[str, Any] = {}
        annotations: Dict[str, Any] = {}

        # Injecting config extensions
        if chat_message_input_disabled is not None:
            conf_fields = {
                "chat_message_input_disabled": chat_message_input_disabled
            }
            conf_cls = getattr(cls, "Config", object)
            namespace["Config"] = type("Config", (conf_cls,), conf_fields)

        # Injecting button extensions
        for name, field_info in kwargs.items():
            buttons_extra = field_info.extra.get("buttons")  # type: ignore
            field_name = f"{cls.__name__}.{name}"

            if not buttons_extra:
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
