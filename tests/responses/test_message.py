import pytest

from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses.enums import ItemStatus, MessagePhase
from aidial_sdk.responses.message import Message
from aidial_sdk.responses.models import (
    UrlCitation,
)
from tests.responses.conftest import (
    _FixedIdContext,
    drain,
)


def _types(ctx: _ResponseContext) -> list[str]:
    return [event["type"] for event in drain(ctx)]


def test_url_citation_defaults_to_the_text_so_far():
    ctx = _FixedIdContext(stream=True)
    text = Message(ctx).create_text().append("Hello")

    text.add_url_citation("https://example.com")
    text.append(", world")

    assert text._part.annotations == [
        UrlCitation(
            url="https://example.com", title="", start_index=0, end_index=5
        )
    ]


def test_append_reuses_the_open_part_of_the_same_kind():
    ctx = _FixedIdContext(stream=True)
    message = Message(ctx)
    text = message.create_text()

    message.append_text("a").append_text("b")

    assert message._item.content == [text._part]
    assert text._part.text == "ab"


def test_set_incomplete():
    ctx = _FixedIdContext(stream=True)

    message = Message(ctx).set_incomplete()
    assert message._item.status == ItemStatus.IN_PROGRESS

    message.close()
    assert message._item.status == ItemStatus.INCOMPLETE


@pytest.mark.parametrize("phase", [MessagePhase.COMMENTARY, "commentary"])
def test_phase_on_creation_rides_added(phase):
    ctx = _FixedIdContext(stream=True)

    Message(ctx, phase=phase)

    assert drain(ctx)[0]["item"]["phase"] == "commentary"


def test_set_phase_reaches_done_only():
    ctx = _FixedIdContext(stream=True)

    Message(ctx).set_phase("commentary").close()

    added, done = drain(ctx)
    assert added["item"]["phase"] is None
    assert done["item"]["phase"] == "commentary"


def test_set_phase_accepts_the_enum():
    message = Message(_FixedIdContext(stream=True))

    message.set_phase(MessagePhase.COMMENTARY)

    assert message._item.phase == MessagePhase.COMMENTARY


def test_content_stream():
    ctx = _FixedIdContext(stream=True)
    message = Message(ctx)

    print("Hello", file=message.content_stream)
    print("world", end="", file=message.create_text().content_stream)

    assert [part.text for part in message._item.content] == [  # type: ignore
        "Hello\n",
        "world",
    ]
