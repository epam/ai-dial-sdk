from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from tests.utils.chunks import (
    check_sse_stream,
    create_function_call_chunk,
    create_single_choice_chunk,
)
from tests.utils.client import create_app_client


class FunctionCaller(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        response.set_response_id("test_id")
        response.set_created(0)

        with response.create_single_choice() as choice:
            choice.append_content("Test content")

            function_call = choice.create_function_call("function_name")
            function_call.append_arguments('{"key')
            function_call.append_arguments('":"')
            function_call.append_arguments('val"}')


def test_function_call_non_streaming():
    response = create_app_client(FunctionCaller()).post(
        "chat/completions", json={"messages": [], "stream": False}
    )

    body = response.json()
    assert body["choices"][0]["message"]["function_call"] == {
        "name": "function_name",
        "arguments": '{"key":"val"}',
    }


def test_function_call_streaming():
    response = create_app_client(FunctionCaller()).post(
        "chat/completions", json={"messages": [], "stream": True}
    )

    check_sse_stream(
        response.iter_lines(),
        [
            create_single_choice_chunk({"role": "assistant"}),
            create_single_choice_chunk({"content": "Test content"}),
            create_function_call_chunk(name="function_name"),
            create_function_call_chunk(arguments='{"key'),
            create_function_call_chunk(arguments='":"'),
            create_function_call_chunk(arguments='val"}'),
            create_single_choice_chunk({}, "function_call"),
        ],
    )
