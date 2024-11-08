import json

from fastapi import Request as FastAPIRequest

from aidial_sdk.chat_completion.request import Request, StaticTool, Tool


def _create_mock_request(json_data):
    async def _async_receive(json_data):
        return {
            "type": "http.request",
            "body": json.dumps(json_data).encode(),
        }

    return FastAPIRequest(
        scope={
            "type": "http",
            "method": "POST",
            "headers": [
                (b"content-type", b"application/json"),
                (b"api-key", b"TEST_API_KEY"),
            ],
            "query_string": "api-version=2024-02-01",
        },
        receive=lambda: _async_receive(json_data),
    )


async def test_with_simple_tools():
    mock_data = {
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
    }

    mock_request = _create_mock_request(mock_data)

    request = await Request.from_request(mock_request, "gpt-3.5-turbo")
    assert request.model == "gpt-3.5-turbo"
    assert request.tools is not None
    assert len(request.tools) == 2
    assert isinstance(request.tools[0], Tool)
    assert request.tools[0].function.name == "test_tool"
    assert isinstance(request.tools[1], Tool)
    assert request.tools[1].function.name == "test_tool_2"


async def test_with_only_static_tools():
    mock_data = {
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
    }

    mock_request = _create_mock_request(mock_data)
    request = await Request.from_request(mock_request, "gpt-3.5-turbo")
    assert request.tools is not None
    assert len(request.tools) == 1
    assert isinstance(request.tools[0], StaticTool)
    assert request.tools[0].type == "static_function"
    assert request.tools[0].static_function.name == "test_static_tool"
    assert request.tools[0].static_function.configuration
    assert (
        request.tools[0].static_function.configuration["datastore"]
        == "test_datastore"
    )
    assert request.tools[0].static_function.configuration["threshold"] == 0.5


async def test_with_mixed_tool_types():
    mock_data = {
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
    }

    mock_request = _create_mock_request(mock_data)
    request = await Request.from_request(mock_request, "gpt-3.5-turbo")
    assert request.tools is not None
    assert len(request.tools) == 2

    # Verify first tool (regular function)
    assert isinstance(request.tools[0], Tool)
    assert request.tools[0].type == "function"
    assert request.tools[0].function.name == "test_tool"

    # Verify second tool (static function)
    assert isinstance(request.tools[1], StaticTool)
    assert request.tools[1].type == "static_function"
    assert request.tools[1].static_function.name == "test_static_tool"
    assert request.tools[1].static_function.configuration
    assert (
        request.tools[1].static_function.configuration["datastore"]
        == "test_datastore"
    )
    assert request.tools[1].static_function.configuration["threshold"] == 0.5
