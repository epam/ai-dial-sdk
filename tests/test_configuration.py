from typing import List, Optional

import pytest

from aidial_sdk.chat_completion import Button
from aidial_sdk.chat_completion.configuration import (
    ButtonField,
    DialFormMetaclass,
    dial_form,
)
from aidial_sdk.pydantic_v1 import BaseModel, Field, ValidationError


class StaticConfiguration_OneButton(BaseModel, metaclass=DialFormMetaclass):
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


class StaticConfiguration_TwoButtons(BaseModel, metaclass=DialFormMetaclass):
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


class StaticConfiguration_OptionalButton(
    BaseModel, metaclass=DialFormMetaclass
):
    int_button_field: Optional[int] = Field(
        default=None,
        buttons=[
            Button(const=10, title="Title1"),
            Button(const=20, title="Title2"),
        ],
    )


def test_configuration_schema():
    actual_schema = StaticConfiguration_OneButton.schema()
    assert actual_schema == {
        "title": "StaticConfiguration_OneButton",
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

    assert StaticConfiguration_OneButton.parse_obj(
        conf
    ) == StaticConfiguration_OneButton(
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
        StaticConfiguration_OneButton.parse_obj(conf)

    assert e.value.errors() == [
        {
            "loc": ("int_button_field",),
            "msg": "unexpected value; permitted: 10, 20",
            "type": "value_error.const",
            "ctx": {"given": 11, "permitted": (10, 20)},
        }
    ]


def test_configuration_parsing_two_buttons_fail():
    conf = {"int_button_field": 11, "str_button_field": "z"}

    with pytest.raises(ValidationError) as e:
        StaticConfiguration_TwoButtons.parse_obj(conf)

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


def test_configuration_parsing_two_buttons_success():
    conf = {"int_button_field": 10, "str_button_field": "a"}
    conf_parsed = StaticConfiguration_TwoButtons.parse_obj(conf)

    assert conf_parsed.int_button_field == 10
    assert conf_parsed.str_button_field == "a"


def test_dynamic_configuration_existing_field():

    class Conf(BaseModel):
        int_field: int
        str_field: str
        buttons_field: int

    conf = dial_form(
        disable_chat_input=True,
        button_fields=[
            ButtonField(
                "buttons_field",
                [
                    Button(const=10, title="Title1"),
                    Button(const=20, title="Title2"),
                ],
            )
        ],
    )(Conf)

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
        "title": "_Conf",
        "type": "object",
    }


def test_dynamic_configuration_new_field():

    class Conf(BaseModel):
        int_field: int
        str_field: str

    conf = dial_form(
        disable_chat_input=True,
        button_fields=[
            ButtonField(
                "buttons_field",
                [
                    Button(const=10, title="Title1"),
                    Button(const=20, title="Title2"),
                ],
            )
        ],
    )(Conf)

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
        "title": "_Conf",
        "type": "object",
    }


def test_dynamic_configuration_conflicting_types():

    class Conf(BaseModel):
        int_field: int
        str_field: str
        buttons_field: str

    with pytest.raises(ValueError) as e:
        dial_form(
            disable_chat_input=True,
            button_fields=[
                ButtonField(
                    "buttons_field",
                    [
                        Button(const=10, title="Title1"),
                        Button(const=20, title="Title2"),
                    ],
                )
            ],
        )(Conf)

    assert (
        str(e.value)
        == "Field Conf.buttons_field has type 'str' but buttons are of type 'int'."
    )


def test_dynamic_configuration_redefinition():

    class Conf(BaseModel):
        pass

    with pytest.raises(ValueError) as e:
        dial_form(
            disable_chat_input=True,
            button_fields=[
                ButtonField(
                    "buttons_field",
                    [Button(const=10, title="Title")],
                ),
                ButtonField(
                    "buttons_field",
                    [Button(const=20, title="Title")],
                ),
            ],
        )(Conf)

    assert str(e.value) == "Field Conf.buttons_field is already defined."


def test_dynamic_configuration_two_buttons():

    class Conf(BaseModel):
        str_button_field: str
        int_button_field: int

    conf = dial_form(
        disable_chat_input=True,
        button_fields=[
            ButtonField(
                "int_button_field",
                [
                    Button(const=10, title="Title1"),
                    Button(const=20, title="Title2"),
                ],
            ),
            ButtonField(
                "str_button_field",
                [
                    Button(const="30", title="Title3"),
                    Button(const="40", title="Title4"),
                ],
            ),
        ],
    )(Conf)

    actual_schema = conf.schema()

    assert actual_schema == {
        "additionalProperties": False,
        "dial:chatMessageInputDisabled": True,
        "properties": {
            "int_button_field": {
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
                "title": "Int Button Field",
                "type": "integer",
            },
            "str_button_field": {
                "dial:widget": "buttons",
                "oneOf": [
                    {
                        "const": "30",
                        "dial:widgetOptions": {
                            "confirmationMessage": None,
                            "populateText": None,
                            "submit": False,
                        },
                        "title": "Title3",
                    },
                    {
                        "const": "40",
                        "dial:widgetOptions": {
                            "confirmationMessage": None,
                            "populateText": None,
                            "submit": False,
                        },
                        "title": "Title4",
                    },
                ],
                "title": "Str Button Field",
                "type": "string",
            },
        },
        "required": [
            "str_button_field",
            "int_button_field",
        ],
        "title": "_Conf",
        "type": "object",
    }
