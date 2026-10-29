import pytest
from anthropic.types import Usage

from aidial_sdk.translators.messages_to_chat_completions.errors import (
    AnthropicErrorType,
)
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
            stream,
            state,
            lambda item: [item.encode()],
            on_finalize=(lambda: [b"done"]) if finalize else None,
            log_context="Test",
        )
    ]
    assert chunks == ([b"a", b"b", b"done"] if finalize else [b"a", b"b"])
    assert stream.closed


async def test_run_sse_stream_turns_exception_into_error_event() -> None:
    stream = FakeStream(["a"], raise_after=RuntimeError("boom"))
    state = AnthropicStreamState("m")
    chunks = [
        chunk
        async for chunk in run_sse_stream(
            stream,
            state,
            lambda item: [item.encode()],
            on_finalize=lambda: [b"unexpected success"],
            log_context="Test",
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


@pytest.mark.parametrize("failed", [False, True])
def test_terminal_stream_emits_no_more_events(failed: bool) -> None:
    state = AnthropicStreamState("m")
    if failed:
        list(state.emit_error(AnthropicErrorType.API, "Internal server error"))
    else:
        list(state.final_events("end_turn", _usage()))
    assert list(state.final_events("end_turn", _usage())) == []
    assert list(state.emit_error(AnthropicErrorType.API, "another error")) == []
