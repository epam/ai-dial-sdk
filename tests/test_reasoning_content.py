import asyncio

from aidial_sdk.chat_completion.choice import Choice
from aidial_sdk.chat_completion.chunks import (
    ContentChunk,
    EndChoiceChunk,
    ReasoningContentChunk,
    StartChoiceChunk,
)
from aidial_sdk.chat_completion.enums import FinishReason
from aidial_sdk.chat_completion.request import Message, Role
from aidial_sdk.utils.merge_chunks import merge


def test_message_reasoning_content_parsing():
    msg = Message(
        role=Role.ASSISTANT,
        content="Final answer",
        reasoning_content="Detailed step-by-step thinking process",
    )
    assert msg.role == Role.ASSISTANT
    assert msg.content == "Final answer"
    assert msg.reasoning_content == "Detailed step-by-step thinking process"


def test_choice_append_reasoning_content():
    queue = asyncio.Queue()
    choice = Choice(queue=queue, choice_index=0)

    choice.open()
    choice.append_reasoning_content("Thinking part 1. ")
    choice.append_reasoning_content("Thinking part 2.")
    choice.append_content("Answer text.")
    choice.close(FinishReason.STOP)

    chunks = []
    while not queue.empty():
        chunks.append(queue.get_nowait())

    assert len(chunks) == 5
    assert isinstance(chunks[0], StartChoiceChunk)
    assert isinstance(chunks[1], ReasoningContentChunk)
    assert chunks[1].content == "Thinking part 1. "
    assert chunks[1].to_dict()["choices"][0]["delta"] == {
        "reasoning_content": "Thinking part 1. "
    }
    assert isinstance(chunks[2], ReasoningContentChunk)
    assert chunks[2].content == "Thinking part 2."
    assert isinstance(chunks[3], ContentChunk)
    assert chunks[3].to_dict()["choices"][0]["delta"] == {
        "content": "Answer text."
    }
    assert isinstance(chunks[4], EndChoiceChunk)

    # Test chunk merge behavior (used for non-streaming response)
    merged = merge(*[c.to_dict() for c in chunks])
    delta = merged["choices"][0]["delta"]
    assert delta["reasoning_content"] == "Thinking part 1. Thinking part 2."
    assert delta["content"] == "Answer text."
    assert merged["choices"][0]["finish_reason"] == "stop"
