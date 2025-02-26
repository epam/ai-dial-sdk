import json

from aidial_sdk._pydantic._compat import (
    model_dump,
)
from aidial_sdk.chat_completion import Message, ResponseFormatJsonSchema, Role
from aidial_sdk.chat_completion.request import ResponseFormatJsonSchemaObject
from tests.utils.pydantic import model_parse, model_parse_json


def test_message_ser():
    msg_obj = Message(role=Role.SYSTEM, content="test")
    actual_dict = model_dump(msg_obj, exclude_none=True)
    expected_dict = {"role": "system", "content": "test"}

    assert json.loads(json.dumps(actual_dict)) == expected_dict


def test_message_deser():
    msg_dict = {"role": "system", "content": "test"}
    actual_obj = model_parse_json(Message, json.dumps(msg_dict))
    expected_obj = Message(role=Role.SYSTEM, content="test")

    assert actual_obj == expected_obj


def test_response_format_serialization():
    format_obj = ResponseFormatJsonSchema(
        type="json_schema",
        json_schema=ResponseFormatJsonSchemaObject(
            description="desc",
            name="name",
            schema={"key": "value"},
        ),
    )

    actual_dict = model_dump(format_obj)

    expected_dict = {
        "type": "json_schema",
        "json_schema": {
            "description": "desc",
            "name": "name",
            "schema": {"key": "value"},
            "strict": False,
        },
    }

    assert actual_dict == expected_dict


def test_response_format_deserialization():
    format_dict = {
        "type": "json_schema",
        "json_schema": {
            "description": "desc",
            "name": "name",
            "schema": {"key": "value"},
        },
    }

    actual_obj = model_parse(ResponseFormatJsonSchema, format_dict)

    expected_obj = ResponseFormatJsonSchema(
        type="json_schema",
        json_schema=ResponseFormatJsonSchemaObject(
            description="desc",
            name="name",
            schema={"key": "value"},
            strict=False,
        ),
    )

    assert actual_obj == expected_obj
