from itertools import zip_longest

import pytest

from aidial_sdk.chat_completion.request import Request, StaticTool, Tool
from tests.utils.chat_completion_validation import validate_chat_completion

TEST_CASES = [
    {
        "messages": [{"role": "user", "content": "Hello"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "test_tool_2",
                    "description": "Test tool 2",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ],
        "model": "gpt-3.5-turbo",
    },
    {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Hello"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "test_tool_2",
                    "description": "Test tool 2",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ],
    },
    {
        "messages": [{"role": "user", "content": "Hello"}],
        "tools": [
            {
                "type": "static_function",
                "static_function": {
                    "name": "test_static_tool",
                    "description": "Test static tool",
                    "configuration": {
                        "datastore": "test_datastore",
                        "threshold": 0.5,
                    },
                },
            },
        ],
        "model": "gpt-3.5-turbo",
    },
    {
        "messages": [{"role": "user", "content": "Hello"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "static_function",
                "static_function": {
                    "name": "test_static_tool",
                    "description": "Test static tool",
                    "configuration": {
                        "datastore": "test_datastore",
                        "threshold": 0.5,
                    },
                },
            },
        ],
        "model": "gpt-3.5-turbo",
    },
]


@pytest.mark.parametrize(
    "mock_data",
    TEST_CASES,
)
def test_tools_parsing(mock_data):

    def _request_validator(r: Request):
        assert r.dict(exclude_none=True) == mock_data
        assert r.tools
        for mock_tool, tool in zip_longest(
            mock_data["tools"], r.tools, fillvalue={}
        ):
            if mock_tool["type"] == "function":
                assert isinstance(tool, Tool)
            elif mock_tool["type"] == "static_function":
                assert isinstance(tool, StaticTool)

    validate_chat_completion(
        input_request=mock_data,
        request_validator=_request_validator,
    )
