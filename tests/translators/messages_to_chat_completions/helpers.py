import json
from collections.abc import AsyncIterator, Iterable, Mapping
from typing import Generic, Literal, TypeVar, cast

from anthropic.types.beta.message_create_params import MessageCreateParams
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta
from openai.types.completion_usage import CompletionUsage

from aidial_sdk.translators.messages_to_chat_completions.chat_completions.to_chat_completions import (
    DialChatCompletionsRequest,
    to_chat_completions_request,
)
from aidial_sdk.translators.messages_to_chat_completions.translation_state import (
    TranslationState,
)


def features_header(**features: object) -> dict[str, str]:
    return {
        "x-dial-deployment-features": json.dumps(
            {
                "temperature": True,
                "cache": False,
                "reasoning_efforts": [],
                "max_completion_tokens_supported": False,
                "tools": True,
                **features,
            }
        )
    }


T = TypeVar("T")


class FakeStream(Generic[T]):
    def __init__(
        self, items: Iterable[T], raise_after: Exception | None = None
    ) -> None:
        self._items = items
        self._raise_after = raise_after
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[T]:
        for item in self._items:
            yield item
        if self._raise_after is not None:
            raise self._raise_after

    async def close(self) -> None:
        self.closed = True


DEPLOYMENT = "gpt-4o"
FinishReason = Literal[
    "stop", "length", "tool_calls", "content_filter", "function_call"
]


def convert(
    body: Mapping[str, object],
    model: str = DEPLOYMENT,
    translation_state: TranslationState | None = None,
) -> DialChatCompletionsRequest:
    return to_chat_completions_request(
        cast(MessageCreateParams, {"model": model, "max_tokens": 100, **body}),
        model,
        translation_state
        if translation_state is not None
        else TranslationState(),
    )


def user(
    content: str | list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    return {"messages": [{"role": "user", "content": content}]}


def parse_anthropic_sse(raw: bytes):
    out = []
    for block in raw.decode().split("\n\n"):
        if not block.strip():
            continue
        event: str | None = None
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data_lines.append(line[len("data: ") :])
        assert event is not None
        out.append((event, json.loads("\n".join(data_lines))))
    return out


def chunk(
    delta: ChoiceDelta | dict[str, object] | None = None,
    finish_reason: FinishReason | None = None,
    id: str = "chatcmpl_1",
    model: str = "gpt-5.5",
    usage: CompletionUsage | None = None,
    choices: list[Choice] | None = None,
) -> ChatCompletionChunk:
    if choices is None:
        if delta is None:
            delta = ChoiceDelta()
        elif isinstance(delta, dict):
            delta = ChoiceDelta.model_validate(delta)
        choices = [Choice(index=0, delta=delta, finish_reason=finish_reason)]
    return ChatCompletionChunk(
        id=id,
        object="chat.completion.chunk",
        created=0,
        model=model,
        choices=choices,
        usage=usage,
    )
