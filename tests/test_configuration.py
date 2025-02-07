from typing import List, Optional

from aidial_sdk.chat_completion import Button, Configuration
from aidial_sdk.pydantic_v1 import Field, ValidationError


class StaticConfiguration(Configuration):
    "Static application configuration"

    _dial_chatMessageInputDisabled = True

    int_field: Optional[int] = Field(
        default=None, description="Int field description"
    )

    str_field: str
    list_field: List[str]

    int_button_field: int = Field(
        title="Integer Button field",
        description="Pick a button",
        buttons=[
            Button(
                const=10,
                submit=True,
                title="Title1",
                confirmationMessage="Conf1",
                populateText="Pop1",
            ),
            Button(
                const=20,
                submit=True,
                title="Title2",
                confirmationMessage="Conf2",
                populateText="Pop2",
            ),
        ],
    )


def test_configuration_schema():
    actual_schema = StaticConfiguration.schema()
    assert actual_schema == {
        "title": "StaticConfiguration",
        "description": "Static application configuration",
        "type": "object",
        "properties": {
            "int_field": {
                "title": "Int Field",
                "type": "integer",
                "description": "Int field description",
            },
            "str_field": {"title": "Str Field", "type": "string"},
            "list_field": {
                "title": "List Field",
                "type": "array",
                "items": {"type": "string"},
            },
            "int_button_field": {
                "title": "Integer Button field",
                "description": "Pick a button",
                "type": "integer",
                "dial:widget": "buttons",
                "oneOf": [
                    {
                        "const": 10,
                        "title": "Title1",
                        "dial:widgetOptions": {
                            "confirmationMessage": "Conf1",
                            "populateText": "Pop1",
                            "submit": True,
                        },
                    },
                    {
                        "const": 20,
                        "title": "Title2",
                        "dial:widgetOptions": {
                            "confirmationMessage": "Conf2",
                            "populateText": "Pop2",
                            "submit": True,
                        },
                    },
                ],
            },
        },
        "required": [
            "str_field",
            "list_field",
            "int_button_field",
        ],
        "additionalProperties": False,
        "dial:chatMessageInputDisabled": True,
    }


def test_configuration_parsing_success():
    conf = {
        "int_field": 10,
        "str_field": "Test",
        "list_field": ["a", "b", "c"],
        "int_button_field": 10,
    }

    assert StaticConfiguration.parse_obj(conf) == StaticConfiguration(
        int_field=10,
        str_field="Test",
        list_field=["a", "b", "c"],
        int_button_field=10,
    )


def test_configuration_parsing_fail():
    conf = {
        "int_field": 10,
        "str_field": "Test",
        "list_field": ["a", "b", "c"],
        "int_button_field": 11,
    }

    try:
        StaticConfiguration.parse_obj(conf)
    except ValidationError as e:
        assert e.errors() == [
            {
                "loc": ("int_button_field",),
                "msg": "unexpected value; permitted: 10, 20",
                "type": "value_error.const",
                "ctx": {"given": 11, "permitted": (10, 20)},
            }
        ]
    else:
        assert False, "Expected ValidationError"
