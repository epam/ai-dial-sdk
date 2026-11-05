import pytest
from anthropic.types import Usage

from aidial_sdk.exceptions import InternalServerError
from aidial_sdk.translators.messages_to_chat_completions.sse_stream import (
    AnthropicStreamState,
    run_sse_stream,
)
from tests.translators.messages_to_chat_completions.helpers import (
    FakeStream,
    parse_anthropic_sse,
)


def _usage() -> Usage:
    return Usage(
        input_tokens=1,
        output_tokens=2,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )


@pytest.mark.parametrize("finalize", [False, True])
async def test_stream_dispatches_items_finalizes_and_closes(
    finalize: bool,
) -> None:
    stream = FakeStream(["a", "b"])
    state = AnthropicStreamState("m")
    chunks = [
        chunk
        async for chunk in run_sse_stream(
            stream.generator,
            state,
            lambda item: [item.encode()],
            on_finalize=(lambda: [b"done"]) if finalize else None,
        )
    ]
    assert chunks == ([b"a", b"b", b"done"] if finalize else [b"a", b"b"])
    assert stream.closed


async def test_run_sse_stream_turns_exception_into_error_event():
    stream = FakeStream(["a"], raise_after=RuntimeError("boom"))
    state = AnthropicStreamState("m")
    chunks = [
        chunk
        async for chunk in run_sse_stream(
            stream.generator,
            state,
            lambda item: [item.encode()],
            on_finalize=lambda: [b"unexpected success"],
        )
    ]
    assert chunks[0] == b"a"
    assert parse_anthropic_sse(b"".join(chunks[1:])) == [
        (
            "error",
            {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": "Internal server error",
                },
            },
        )
    ]
    assert stream.closed is True


async def test_a_stream_left_early_is_closed():
    stream = FakeStream(["a", "b"])

    def _fail(item: str) -> list[bytes]:
        raise RuntimeError("boom")

    chunks = [
        chunk
        async for chunk in run_sse_stream(
            stream.generator, AnthropicStreamState("m"), _fail
        )
    ]

    assert [name for name, _ in parse_anthropic_sse(b"".join(chunks))] == [
        "error"
    ]
    assert stream.closed


@pytest.mark.parametrize("failed", [False, True])
def test_terminal_stream_emits_no_more_events(failed: bool):
    state = AnthropicStreamState("m")
    if failed:
        list(state.emit_error(InternalServerError("Internal server error")))
    else:
        list(state.final_events("end_turn", _usage()))
    assert list(state.final_events("end_turn", _usage())) == []
    assert list(state.emit_error(InternalServerError("another error"))) == []
