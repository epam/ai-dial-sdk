from dataclasses import dataclass
from typing import Any, Dict, Generic, List, Literal, Optional, Type, TypeVar

from pydantic.v1.fields import FieldInfo
from pydantic.v1.main import ModelMetaclass
from pydantic.v1.validators import make_literal_validator

from aidial_sdk.pydantic_v1 import BaseModel, validator

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


class _ConfigurationMetaclass(ModelMetaclass):
    def __new__(mcs, name, bases, namespace: dict, **kwargs):
        validators = {}
        for field_name, field_info in namespace.items():
            if not isinstance(field_info, FieldInfo):
                continue

            buttons = field_info.extra.get("buttons") or []
            assert all(isinstance(button, Button) for button in buttons)

            consts = tuple(button.const for button in buttons)
            literal_type = Literal[consts]
            literal_validator = make_literal_validator(literal_type)

            def _validate(value, values, config, field):
                return literal_validator(value)

            validators[f"_validate_{field_name}"] = validator(
                field_name, allow_reuse=True
            )(_validate)

        namespace.update(validators)

        return super().__new__(mcs, name, bases, namespace, **kwargs)


class Configuration(BaseModel, metaclass=_ConfigurationMetaclass):
    class Config:
        extra = "forbid"

        @staticmethod
        def schema_extra(schema, model: Type["Configuration"]):
            model._handle_top_level_extensions(schema)
            model._handle_buttons_extension(schema)

    @classmethod
    def _handle_top_level_extensions(cls, schema: Dict[str, Any]) -> None:
        if (
            disable_input := getattr(
                cls, "_dial_chatMessageInputDisabled", None
            )
        ) is not None:
            schema["dial:chatMessageInputDisabled"] = disable_input is True

    @classmethod
    def _handle_buttons_extension(cls, schema: Dict[str, Any]) -> None:
        for prop in schema.get("properties", {}).values():
            if buttons := prop.pop("buttons", None):
                button_schemas: List[dict] = []
                for button in buttons:
                    assert isinstance(button, Button)
                    button_schemas.append(button.schema())
                prop["dial:widget"] = "buttons"
                prop["oneOf"] = button_schemas
