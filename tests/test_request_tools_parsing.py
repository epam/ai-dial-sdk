from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from aidial_sdk.application import DIALApp
from aidial_sdk.chat_completion.request import StaticTool, Tool
from examples.echo.app import EchoApplication

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
    dial_app = DIALApp()
    chat_completion = Mock(wraps=EchoApplication())
    dial_app.add_chat_completion("test_app", chat_completion)

    test_app = TestClient(dial_app)

    test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json=mock_data,
        headers={"Api-Key": "TEST_API_KEY"},
    )

    args, _ = chat_completion.chat_completion.call_args
    request, _ = args

    request_dict = request.dict(exclude_none=True)
    for key in mock_data:
        assert request_dict[key] == mock_data[key]
    assert request.tools and len(request.tools) == len(mock_data["tools"])
    for mock_tool, tool in zip(mock_data["tools"], request.tools):
        if mock_tool["type"] == "function":
            assert isinstance(tool, Tool)
        elif mock_tool["type"] == "static_function":
            assert isinstance(tool, StaticTool)
