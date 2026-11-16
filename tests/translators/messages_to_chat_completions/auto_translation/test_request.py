import json

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import (
    Function,
    FunctionCall,
    Message,
    Request,
    Response,
    Role,
    Tool,
    ToolCall,
)
from tests.translators.messages_to_chat_completions.auto_translation.helpers import (
    DUMMY_API_KEY,
    AppClient,
    ScriptedChatCompletion,
    replying,
)


async def test_the_impl_receives_the_translated_request(stream: bool):
    foo = replying("Sunny")
    app = DIALApp().add_chat_completion(
        "foo", foo, expose_as_anthropic_messages=True
    )

    async with AppClient(app).anthropic() as client:
        await client.final_message(
            stream=stream,
            max_tokens=100,
            system="Be brief",
            temperature=0.5,
            stop_sequences=["STOP"],
            tools=[
                {
                    "name": "get_weather",
                    "description": "Weather in a city",
                    "input_schema": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                }
            ],
            tool_choice={"type": "auto"},
            messages=[
                {"role": "user", "content": "Weather in Paris?"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "get_weather",
                            "input": {"city": "Paris"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "content": "Sunny",
                        }
                    ],
                },
            ],
        )

    [request] = foo.requests
    assert request.messages == [
        Message(role=Role.SYSTEM, content="Be brief"),
        Message(role=Role.USER, content="Weather in Paris?"),
        Message(
            role=Role.ASSISTANT,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    type="function",
                    function=FunctionCall(
                        name="get_weather", arguments='{"city": "Paris"}'
                    ),
                )
            ],
        ),
        Message(role=Role.TOOL, content="Sunny", tool_call_id="call_1"),
    ]
    assert request.tools == [
        Tool(
            type="function",
            function=Function(
                name="get_weather",
                description="Weather in a city",
                parameters={
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                },
                strict=False,
            ),
        )
    ]
    assert request.tool_choice == "auto"
    assert request.temperature == 0.5
    assert request.stop == ["STOP"]
    assert request.max_completion_tokens == 100
    assert request.stream is stream


async def test_the_impl_receives_the_dial_context_of_the_request(
    stream: bool,
) -> None:
    foo = replying("Hi from foo")
    app = DIALApp().add_chat_completion(
        "foo", foo, expose_as_anthropic_messages=True
    )

    async with AppClient(app).anthropic() as client:
        await client.final_message(stream=stream)

    [request] = foo.requests
    assert request.deployment_id == "foo"
    assert request.api_key == DUMMY_API_KEY


async def test_the_impl_reads_the_translated_body_both_as_json_and_as_bytes(
    stream: bool,
):
    bodies: list[tuple[dict, dict]] = []

    async def _read_body(request: Request, response: Response) -> None:
        original = request.original_request
        bodies.append(
            (await original.json(), json.loads(await original.body()))
        )
        with response.create_single_choice() as choice:
            choice.append_content("Hi")

    app = DIALApp().add_chat_completion(
        "foo",
        ScriptedChatCompletion(_read_body),
        expose_as_anthropic_messages=True,
    )

    async with AppClient(app).anthropic() as client:
        await client.final_message(stream=stream)

    [(as_json, as_bytes)] = bodies
    assert as_json == as_bytes
    assert as_json["messages"] == [{"role": "user", "content": "Hello"}]
