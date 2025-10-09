from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    get_args,
)

from aidial_sdk._pydantic import (
    PYDANTIC_V2,
    BaseModel,
    FieldInfo,
    ModelMetaclass,
    make_literal_validator,
    validator,
)
from aidial_sdk._pydantic._model_config import ModelConfigWrapper

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
    def __new__(
        mcs,  # pyright: ignore[reportSelfClsParameterName]
        name,
        bases,
        namespace: Dict,
        **kwargs,
    ):
        # Inject buttons validators

        button_fields: Dict[str, List[Button]] = {}
        validators: Dict[str, Any] = {}

        for field_name, field_info in namespace.items():
            if (buttons_extra := _extract_buttons_field(field_info)) is None:
                continue

            buttons = _get_buttons(f"{name}.{field_name}", buttons_extra)
            if not buttons:
                continue

            button_fields[field_name] = buttons

            enum_values = tuple(button.const for button in buttons)
            validators[f"_validate_{field_name}"] = _create_field_validator(
                field_name, enum_values
            )

        namespace.update(validators)

        # Inject JSON schema post processing

        model_config = ModelConfigWrapper.create(None, namespace)
        model_config["extra"] = "forbid"

        def _on_schema(json_schema: Dict[str, Any]) -> None:
            _add_model_config_extensions(model_config, json_schema)
            _add_button_fields(name, json_schema, button_fields)

        model_config.post_process_schema(_on_schema)

        return super().__new__(mcs, name, bases, namespace, **kwargs)


def _add_model_config_extensions(
    model_config: ModelConfigWrapper, json_schema: Dict[str, Any]
) -> None:
    if (
        disable_input := model_config["chat_message_input_disabled"]
    ) is not None:
        json_schema["dial:chatMessageInputDisabled"] = disable_input is True


def _add_button_fields(
    cls_name: str,
    json_schema: Dict[str, Any],
    button_fields: Dict[str, List[Button]],
) -> None:
    for field_name, buttons in button_fields.items():
        prop = json_schema["properties"][field_name]
        prop.pop("buttons", None)

        button_schemas = [button.schema() for button in buttons]

        prop["dial:widget"] = "buttons"
        prop["oneOf"] = button_schemas

        if (anyOf := prop.pop("anyOf", None)) is not None:
            # Optional types are translated in Pydantic V2 to
            # {'anyOf': [{'type': 'integer'}, {'type': 'null'}], 'default': null}
            # which conflicts with the 'oneOf' definition.
            types = {schema["type"] for schema in anyOf}
            types.discard("null")
            if len(types) != 1:
                raise ValueError(
                    f"Field {cls_name}.{field_name} has conflicting types {types}."
                )
            prop["type"] = types.pop()
            prop.pop("default", None)

        if prop["type"] not in _SUPPORTED_BUTTON_TYPES:
            ts = ", ".join(f"{ty!r}" for ty in _SUPPORTED_BUTTON_TYPES)

            raise ValueError(
                f"Button value must be a one of the following types: {ts}. "
                f"However, field {cls_name}.{field_name} has type {prop['type']!r}."
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

        # Inject model config extensions
        model_config = ModelConfigWrapper.create(cls, namespace)
        if chat_message_input_disabled is not None:
            model_config["chat_message_input_disabled"] = (
                chat_message_input_disabled
            )

        # Inject button extensions
        annotations: Dict[str, Any] = {}

        for name, field_info in kwargs.items():
            field_name = f"{cls.__name__}.{name}"

            if (buttons_extra := _extract_buttons_field(field_info)) is None:
                raise ValueError(
                    f"Field descriptor of {field_name} is missing 'buttons' parameter."
                )

            buttons = _get_buttons(field_name, buttons_extra)
            button_type = type(buttons[0].const)

            if field_type := cls.__annotations__.get(name):
                field_base_type = _get_base_type(field_type)
                if field_base_type != button_type:
                    raise ValueError(
                        f"Field {field_name} has type {field_base_type} "
                        f"but buttons are of type {button_type}."
                    )
            else:
                field_type = button_type

            namespace[name] = field_info
            annotations[name] = field_type

        namespace["__annotations__"] = annotations

        cls_name = f"_{cls.__name__}"
        return FormMetaclass(cls_name, (cls,), namespace)  # type: ignore

    return _create_class


def _create_field_validator(field_name: str, enum_values: Sequence[Any]):
    literal_type = Literal[enum_values]
    literal_validator = make_literal_validator(literal_type)

    if PYDANTIC_V2:
        return validator(field_name)(literal_validator)
    else:

        def _check_value(value, values, config, field):
            return literal_validator(value)

        return validator(field_name, allow_reuse=True)(_check_value)


def _get_base_type(tp: Type[_T]) -> Type[_T]:
    """Returns T if given Optional[T], otherwise returns the type unchanged."""
    args = get_args(tp)
    if len(args) == 2 and type(None) in args:
        return next(arg for arg in args if arg is not type(None))
    return tp


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
