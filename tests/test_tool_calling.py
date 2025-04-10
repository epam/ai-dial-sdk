from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from tests.utils.chunks import (
    check_sse_stream,
    create_single_choice_chunk,
    create_tool_call_chunk,
)
from tests.utils.client import create_app_client


class ToolCaller(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        response.set_response_id("test_id")
        response.set_created(0)

        with response.create_single_choice() as choice:
            choice.append_content("Test content")

            tool_call = choice.create_function_tool_call("id", "test_tool")
            tool_call.append_arguments('{"key')
            tool_call.append_arguments('":"')
            tool_call.append_arguments('val"}')


def test_tool_call_non_streaming():
    response = create_app_client(ToolCaller()).post(
        "chat/completions", json={"messages": [], "stream": False}
    )

    body = response.json()
    assert body["choices"][0]["message"]["tool_calls"] == [
        {
            "function": {
                "arguments": '{"key":"val"}',
                "name": "test_tool",
            },
            "id": "id",
            "type": "function",
        },
    ]


def test_tool_call_streaming():
    response = create_app_client(ToolCaller()).post(
        "chat/completions", json={"messages": [], "stream": True}
    )

    check_sse_stream(
        response.iter_lines(),
        [
            create_single_choice_chunk({"role": "assistant"}),
            create_single_choice_chunk({"content": "Test content"}),
            create_tool_call_chunk(
                0, type="function", id="id", name="test_tool"
            ),
            create_tool_call_chunk(0, arguments='{"key'),
            create_tool_call_chunk(0, arguments='":"'),
            create_tool_call_chunk(0, arguments='val"}'),
            create_single_choice_chunk({}, "tool_call"),
        ],
    )
