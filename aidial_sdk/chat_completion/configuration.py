from dataclasses import dataclass
from typing import Any, Dict, Generic, List, Literal, Optional, Type, TypeVar

from pydantic.v1.fields import FieldInfo
from pydantic.v1.main import ModelMetaclass
from pydantic.v1.validators import make_literal_validator

from aidial_sdk.pydantic_v1 import BaseModel, Field, validator

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


class ConfigurationMetaclass(ModelMetaclass):
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

            ConfigurationMetaclass._handle_top_level_extensions(model, schema)
            ConfigurationMetaclass._handle_buttons_extension(model, schema)

        config.schema_extra = staticmethod(new_schema_extra)  # type: ignore

        return cls

    @staticmethod
    def _handle_top_level_extensions(
        model: Type[BaseModel], schema: Dict[str, Any]
    ) -> None:
        if (
            disable_input := getattr(
                model, "_dial_chatMessageInputDisabled", None
            )
        ) is not None:
            schema["dial:chatMessageInputDisabled"] = disable_input is True

    @staticmethod
    def _handle_buttons_extension(
        model: Type[BaseModel], schema: Dict[str, Any]
    ) -> None:
        for prop in schema.get("properties", {}).values():
            if buttons := prop.pop("buttons", None):
                button_schemas: List[dict] = []
                for button in buttons:
                    assert isinstance(button, Button)
                    button_schemas.append(button.schema())
                prop["dial:widget"] = "buttons"
                prop["oneOf"] = button_schemas


def create_configuration_class(
    *,
    model: Type[BaseModel],
    buttons: List[Button] = [],
    disable_chat_input: bool = False,
) -> Type[BaseModel]:
    class _Configuration(model, metaclass=ConfigurationMetaclass):
        _dial_chatMessageInputDisabled = disable_chat_input
        buttons_field: int = Field(buttons=buttons)

    return _Configuration
