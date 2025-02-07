from typing import List, Optional

import pytest

from aidial_sdk.chat_completion import Button
from aidial_sdk.chat_completion.configuration import (
    ConfigurationMetaclass,
    create_configuration_class,
)
from aidial_sdk.pydantic_v1 import BaseModel, Field, ValidationError


class StaticConfiguration1(BaseModel, metaclass=ConfigurationMetaclass):
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


class StaticConfiguration2(BaseModel, metaclass=ConfigurationMetaclass):
    int_button_field: int = Field(
        buttons=[
            Button(const=10, title="Title1"),
            Button(const=20, title="Title2"),
        ],
    )

    str_button_field: str = Field(
        buttons=[
            Button(const="a", title="Title3"),
            Button(const="b", title="Title4"),
        ],
    )


def test_configuration_schema():
    actual_schema = StaticConfiguration1.schema()
    assert actual_schema == {
        "title": "StaticConfiguration1",
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

    assert StaticConfiguration1.parse_obj(conf) == StaticConfiguration1(
        int_field=10,
        str_field="Test",
        list_field=["a", "b", "c"],
        int_button_field=10,
    )


def test_configuration_parsing_one_button_fail():
    conf = {
        "int_field": 10,
        "str_field": "Test",
        "list_field": ["a", "b", "c"],
        "int_button_field": 11,
    }

    with pytest.raises(ValidationError) as e:
        StaticConfiguration1.parse_obj(conf)

    assert e.value.errors() == [
        {
            "loc": ("int_button_field",),
            "msg": "unexpected value; permitted: 10, 20",
            "type": "value_error.const",
            "ctx": {"given": 11, "permitted": (10, 20)},
        }
    ]


def test_configuration_parsing_two_buttons_fails():
    conf = {"int_button_field": 11, "str_button_field": "z"}

    with pytest.raises(ValidationError) as e:
        StaticConfiguration2.parse_obj(conf)

    assert e.value.errors() == [
        {
            "ctx": {"given": 11, "permitted": (10, 20)},
            "loc": ("int_button_field",),
            "msg": "unexpected value; permitted: 10, 20",
            "type": "value_error.const",
        },
        {
            "ctx": {"given": "z", "permitted": ("a", "b")},
            "loc": ("str_button_field",),
            "msg": "unexpected value; permitted: 'a', 'b'",
            "type": "value_error.const",
        },
    ]


class SimpleConfiguration(BaseModel):
    int_field: int
    str_field: str


def test_dynamic_configuration():
    conf = create_configuration_class(
        model=SimpleConfiguration,
        buttons=[
            Button(const=10, title="Title1"),
            Button(const=20, title="Title2"),
        ],
        disable_chat_input=True,
    )

    actual_schema = conf.schema()

    assert actual_schema == {
        "additionalProperties": False,
        "dial:chatMessageInputDisabled": True,
        "properties": {
            "buttons_field": {
                "dial:widget": "buttons",
                "oneOf": [
                    {
                        "const": 10,
                        "dial:widgetOptions": {
                            "confirmationMessage": None,
                            "populateText": None,
                            "submit": False,
                        },
                        "title": "Title1",
                    },
                    {
                        "const": 20,
                        "dial:widgetOptions": {
                            "confirmationMessage": None,
                            "populateText": None,
                            "submit": False,
                        },
                        "title": "Title2",
                    },
                ],
                "title": "Buttons Field",
                "type": "integer",
            },
            "int_field": {
                "title": "Int Field",
                "type": "integer",
            },
            "str_field": {
                "title": "Str Field",
                "type": "string",
            },
        },
        "required": [
            "int_field",
            "str_field",
            "buttons_field",
        ],
        "title": "_Configuration",
        "type": "object",
    }
