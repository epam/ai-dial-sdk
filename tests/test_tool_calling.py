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

            tool_call1 = choice.create_function_tool_call(
                "tool_call_id1", "tool_name"
            )
            tool_call1.append_arguments('{"key')
            tool_call1.append_arguments('":"')
            tool_call1.append_arguments('val"}')

            choice.create_function_tool_call(
                "tool_call_id2", "tool_name", '{"foo":"bar"}'
            )


def test_tool_call_non_streaming():
    response = create_app_client(ToolCaller()).post(
        "chat/completions", json={"messages": [], "stream": False}
    )

    body = response.json()
    assert body["choices"][0]["message"]["tool_calls"] == [
        {
            "id": "tool_call_id1",
            "type": "function",
            "function": {
                "name": "tool_name",
                "arguments": '{"key":"val"}',
            },
        },
        {
            "id": "tool_call_id2",
            "type": "function",
            "function": {
                "name": "tool_name",
                "arguments": '{"foo":"bar"}',
            },
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
                0, type="function", id="tool_call_id1", name="tool_name"
            ),
            create_tool_call_chunk(0, arguments='{"key'),
            create_tool_call_chunk(0, arguments='":"'),
            create_tool_call_chunk(0, arguments='val"}'),
            create_tool_call_chunk(
                1,
                type="function",
                id="tool_call_id2",
                name="tool_name",
                arguments='{"foo":"bar"}',
            ),
            create_single_choice_chunk({}, "tool_calls"),
        ],
    )
