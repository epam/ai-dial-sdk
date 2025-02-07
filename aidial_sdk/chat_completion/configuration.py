from dataclasses import dataclass
from typing import Any, Dict, Generic, List, Literal, Optional, Type, TypeVar

from pydantic.v1.validators import make_literal_validator

from aidial_sdk.pydantic_v1 import BaseModel, root_validator

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


class Configuration(BaseModel):
    class Config:
        extra = "forbid"

        @staticmethod
        def schema_extra(schema, model: Type["Configuration"]):
            model._handle_top_level_extensions(schema)
            model._handle_buttons_extension(schema)

    @root_validator()
    def _validate_button_value(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        for field_name, field in cls.__fields__.items():
            buttons = field.field_info.extra.get("buttons")
            if buttons and field_name in values:
                value = values[field_name]
                type = Literal[tuple(button.const for button in buttons)]
                validator = make_literal_validator(type)
                validator(value)

        return values

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
