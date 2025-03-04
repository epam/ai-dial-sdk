from typing import List, Optional

import pytest
from pydantic import BaseModel, Field, ValidationError

from aidial_sdk._pydantic._compat import PYDANTIC_V2
from aidial_sdk.chat_completion import Button
from aidial_sdk.chat_completion.form import FormMetaclass, form
from tests.utils._pydantic import model_json_schema, model_parse


class StaticConfiguration_OneButton(BaseModel, metaclass=FormMetaclass):
    "Static application configuration"

    class Config:
        chat_message_input_disabled = True

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


class StaticConfiguration_TwoButtons(BaseModel, metaclass=FormMetaclass):
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


class StaticConfiguration_OptionalButton(BaseModel, metaclass=FormMetaclass):
    int_button_field: Optional[int] = Field(
        default=None,
        buttons=[
            Button(const=10, title="Title1"),
            Button(const=20, title="Title2"),
        ],
    )


def test_configuration_optional_button_schema():
    actual_schema = model_json_schema(StaticConfiguration_OptionalButton)
    assert actual_schema == {
        "title": "StaticConfiguration_OptionalButton",
        "type": "object",
        "properties": {
            "int_button_field": {
                "title": "Int Button Field",
                "type": "number",
                "dial:widget": "buttons",
                "oneOf": [
                    {
                        "const": 10,
                        "title": "Title1",
                        "dial:widgetOptions": {
                            "confirmationMessage": None,
                            "populateText": None,
                            "submit": False,
                        },
                    },
                    {
                        "const": 20,
                        "title": "Title2",
                        "dial:widgetOptions": {
                            "confirmationMessage": None,
                            "populateText": None,
                            "submit": False,
                        },
                    },
                ],
            },
        },
        "additionalProperties": False,
    }


def test_configuration_optional_button_parsing_success():
    conf = {}

    assert (
        model_parse(StaticConfiguration_OptionalButton, conf)
        == StaticConfiguration_OptionalButton()
    )


def test_configuration_one_button_schema():
    actual_schema = model_json_schema(StaticConfiguration_OneButton)
    extra_fields = {}
    if PYDANTIC_V2:
        extra_fields["anyOf"] = [{"type": "integer"}, {"type": "null"}]
        extra_fields["default"] = None
    else:
        extra_fields["type"] = "integer"

    assert actual_schema == {
        "title": "StaticConfiguration_OneButton",
        "description": "Static application configuration",
        "type": "object",
        "properties": {
            "int_field": {
                "title": "Int Field",
                "description": "Int field description",
                **extra_fields,
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
                "type": "number",
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

    assert model_parse(
        StaticConfiguration_OneButton, conf
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
        model_parse(StaticConfiguration_OneButton, conf)

    errors = e.value.errors()

    assert len(errors) == 1
    assert "unexpected value; permitted: 10, 20" in errors[0]["msg"]


def test_configuration_parsing_two_buttons_fail():
    conf = {"int_button_field": 11, "str_button_field": "z"}

    with pytest.raises(ValidationError) as e:
        model_parse(StaticConfiguration_TwoButtons, conf)

    errors = e.value.errors()

    assert len(errors) == 2
    assert "unexpected value; permitted: 10, 20" in errors[0]["msg"]
    assert "unexpected value; permitted: 'a', 'b'" in errors[1]["msg"]


def test_configuration_parsing_two_buttons_success():
    conf = {"int_button_field": 10, "str_button_field": "a"}
    conf_parsed = model_parse(StaticConfiguration_TwoButtons, conf)

    assert conf_parsed.int_button_field == 10
    assert conf_parsed.str_button_field == "a"


def test_dynamic_configuration_input_disabled_static():
    class Conf(BaseModel):
        class Config:
            chat_message_input_disabled = True

    conf = form()(Conf)

    assert model_json_schema(conf)["dial:chatMessageInputDisabled"] is True


def test_dynamic_configuration_input_disabled_dynamic():
    class Conf(BaseModel):
        class Config:
            extra = "forbid"

    conf = form(chat_message_input_disabled=True)(Conf)

    assert model_json_schema(conf)["dial:chatMessageInputDisabled"] is True


def test_dynamic_configuration_input_disabled_omitted():
    class Conf(BaseModel):
        class Config:
            extra = "forbid"

    conf = form()(Conf)

    assert model_json_schema(conf).get("dial:chatMessageInputDisabled") is None


def test_dynamic_configuration_input_disabled_overwrite1():
    class Conf(BaseModel):
        class Config:
            chat_message_input_disabled = False

    conf = form(chat_message_input_disabled=True)(Conf)

    assert model_json_schema(conf)["dial:chatMessageInputDisabled"] is True


def test_dynamic_configuration_input_disabled_overwrite2():
    class Conf(BaseModel):
        class Config:
            chat_message_input_disabled = True

    conf = form(chat_message_input_disabled=False)(Conf)

    assert model_json_schema(conf)["dial:chatMessageInputDisabled"] is False


def test_dynamic_configuration_existing_field():
    class Conf(BaseModel):
        int_field: int
        str_field: str
        buttons_field: int

    conf = form(
        chat_message_input_disabled=True,
        buttons_field=Field(
            buttons=[
                Button(const=10, title="Title1"),
                Button(const=20, title="Title2"),
            ]
        ),
    )(Conf)

    actual_schema = model_json_schema(conf)

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
                "type": "number",
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

    conf = form(
        chat_message_input_disabled=True,
        buttons_field=Field(
            buttons=[
                Button(const=10, title="Title1"),
                Button(const=20, title="Title2"),
            ]
        ),
    )(Conf)

    actual_schema = model_json_schema(conf)

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
                "type": "number",
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
        form(
            chat_message_input_disabled=True,
            buttons_field=Field(
                buttons=[
                    Button(const=10, title="Title1"),
                    Button(const=20, title="Title2"),
                ],
            ),
        )(Conf)

    assert (
        str(e.value)
        == "Field Conf.buttons_field has type <class 'str'> but buttons are of type <class 'int'>."
    )


def test_dynamic_configuration_optional_type_parsing_success():
    class Conf(BaseModel):
        int_field: int
        str_field: str
        buttons_field: Optional[int]

    conf = form(
        chat_message_input_disabled=True,
        buttons_field=Field(
            buttons=[
                Button(const=10, title="Title1"),
                Button(const=20, title="Title2"),
            ]
        ),
    )(Conf)

    conf_value = {"int_field": 10, "str_field": "Test", "buttons_field": 10}
    parsed_conf = model_parse(conf, conf_value)

    assert parsed_conf.int_field == 10
    assert parsed_conf.str_field == "Test"
    assert parsed_conf.buttons_field == 10


def test_dynamic_configuration_decorator_optional_type_parsing_success():
    @form(
        chat_message_input_disabled=True,
        buttons_field=Field(
            buttons=[
                Button(const=10, title="Title1"),
                Button(const=20, title="Title2"),
            ]
        ),
    )
    class Conf(BaseModel):
        int_field: int
        str_field: str
        buttons_field: Optional[int]

    conf_value = {"int_field": 10, "str_field": "Test", "buttons_field": 10}
    parsed_conf = model_parse(Conf, conf_value)

    assert parsed_conf.int_field == 10
    assert parsed_conf.str_field == "Test"
    assert parsed_conf.buttons_field == 10


def test_dynamic_configuration_two_buttons():
    class Conf(BaseModel):
        int_button_field: int
        float_button_field: float

    conf = form(
        chat_message_input_disabled=True,
        int_button_field=Field(
            description="Number of floors",
            buttons=[
                Button(const=10, title="Title1"),
                Button(const=20, title="Title2"),
            ],
        ),
        float_button_field=Field(
            description="Temperature",
            buttons=[
                Button(const=30.1, title="Title3"),
                Button(const=40.1, title="Title4"),
            ],
        ),
    )(Conf)

    actual_schema = model_json_schema(conf)

    assert actual_schema == {
        "additionalProperties": False,
        "dial:chatMessageInputDisabled": True,
        "properties": {
            "int_button_field": {
                "dial:widget": "buttons",
                "description": "Number of floors",
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
                "type": "number",
            },
            "float_button_field": {
                "dial:widget": "buttons",
                "description": "Temperature",
                "oneOf": [
                    {
                        "const": 30.1,
                        "dial:widgetOptions": {
                            "confirmationMessage": None,
                            "populateText": None,
                            "submit": False,
                        },
                        "title": "Title3",
                    },
                    {
                        "const": 40.1,
                        "dial:widgetOptions": {
                            "confirmationMessage": None,
                            "populateText": None,
                            "submit": False,
                        },
                        "title": "Title4",
                    },
                ],
                "title": "Float Button Field",
                "type": "number",
            },
        },
        "required": [
            "int_button_field",
            "float_button_field",
        ],
        "title": "_Conf",
        "type": "object",
    }


def test_configuration_invalid_button_type():
    with pytest.raises(ValueError) as e:

        class _Conf(BaseModel, metaclass=FormMetaclass):
            button_field: str = Field(
                buttons=[
                    Button(const="10", title="Title1"),
                    Button(const="20", title="Title2"),
                ],
            )

        model_json_schema(_Conf)

    assert (
        str(e.value)
        == "Button value must be a number. However, field _Conf.button_field has type 'string'."
    )


def test_configuration_missing_buttons():
    with pytest.raises(ValueError) as e:

        class _Conf(BaseModel, metaclass=FormMetaclass):
            button_field: int

        _Conf2 = form(button_field=Field(default=43))(_Conf)
        model_json_schema(_Conf2)

    assert (
        str(e.value)
        == "Field descriptor of _Conf.button_field is missing 'buttons' parameter."
    )


def test_configuration_invalid_buttons_type():
    with pytest.raises(ValueError) as e:

        class _Conf(BaseModel, metaclass=FormMetaclass):
            button_field: int

        _Conf2 = form(button_field=Field(default=43, buttons="test"))(_Conf)
        model_json_schema(_Conf2)

    assert (
        str(e.value)
        == "'buttons' parameter of the field descriptor for _Conf.button_field must be a list, but got str."
    )


def test_configuration_invalid_buttons_elem_type():
    with pytest.raises(ValueError) as e:

        class _Conf(BaseModel, metaclass=FormMetaclass):
            button_field: int

        _Conf2 = form(button_field=Field(default=43, buttons=["test"]))(_Conf)
        model_json_schema(_Conf2)

    assert (
        str(e.value)
        == "'buttons' parameter of the field descriptor for _Conf.button_field must be a list of Button objects."
    )
