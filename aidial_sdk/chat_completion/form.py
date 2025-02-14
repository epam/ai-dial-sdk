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
    get_args,
)

from pydantic.v1.fields import FieldInfo
from pydantic.v1.validators import make_literal_validator

from aidial_sdk.pydantic_v1 import BaseModel, Field, ModelMetaclass, validator

_T = TypeVar("_T")


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


@dataclass
class ButtonField(Generic[_T]):
    name: str
    options: List[Button[_T]]


class FormMetaclass(ModelMetaclass):
    def __new__(mcs, name, bases, namespace: dict, **kwargs):
        # Inject buttons validators

        validators = {}
        for field_name, field_info in namespace.items():
            if not isinstance(field_info, FieldInfo):
                continue

            buttons = field_info.extra.get("buttons")
            if not buttons:
                continue

            assert all(isinstance(button, Button) for button in buttons)

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

            _handle_top_level_extensions(model, schema)
            _handle_buttons_extension(schema)

        config.schema_extra = staticmethod(new_schema_extra)  # type: ignore

        return cls


def _handle_top_level_extensions(
    model: Type[BaseModel], schema: Dict[str, Any]
) -> None:
    if (
        disable_input := getattr(model, "_dial_chatMessageInputDisabled", None)
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

            # NOTE: The meta schema of the DIAL forms only supports
            # 'number' type, so we convert 'integer' to 'number'.
            # Could be removed once this restriction is lifted.
            if prop["type"] == "integer":
                prop["type"] = "number"

            # NOTE: The meta schema of the DIAL forms only supports 'number' type.
            # Could be removed once this restriction is lifted.
            if prop["type"] != "number":
                raise ValueError(
                    f"Button value must be a number. However, field {schema['title']}.{prop_name} has type {prop['type']!r}."
                )


_Model = TypeVar("_Model", bound=BaseModel)


def _get_base_type(tp: Type[_T]) -> Type[_T]:
    """Returns T if given Optional[T], otherwise returns the type unchanged."""
    args = get_args(tp)
    if len(args) == 2 and type(None) in args:
        return next(arg for arg in args if arg is not type(None))
    return tp


def form(
    *,
    disable_chat_input: bool = False,
    button_fields: Optional[List[ButtonField]] = None,
) -> Callable[[Type[_Model]], Type[_Model]]:
    def _create_class(model: Type[_Model]) -> Type[_Model]:
        namespace: Dict[str, Any] = {
            "_dial_chatMessageInputDisabled": disable_chat_input,
        }
        annotations: Dict[str, Any] = {}

        for button_field in button_fields or []:
            name = button_field.name
            buttons = button_field.options

            if name in namespace:
                raise ValueError(
                    f"Field {model.__name__}.{name} is already defined."
                )

            namespace[name] = Field(..., buttons=buttons)

            button_type = type(buttons[0].const)
            if field_type := model.__annotations__.get(name):
                annotations[name] = field_type
                field_type_base = _get_base_type(field_type)
                if field_type_base != button_type:
                    raise ValueError(
                        f"Field {model.__name__}.{name} has type {field_type_base} "
                        f"but buttons are of type {button_type}."
                    )
            else:
                annotations[name] = button_type

        if annotations:
            namespace["__annotations__"] = annotations

        cls_name = f"_{model.__name__}"
        return FormMetaclass(cls_name, (model,), namespace)  # type: ignore

    return _create_class
