from aidial_sdk.responses.enums import ItemStatus
from aidial_sdk.responses.reasoning import (
    Reasoning,
)
from tests.responses.conftest import (
    _FixedIdContext,
)


def test_summary_and_content_have_independent_indices():
    reasoning = Reasoning(_FixedIdContext(stream=True))

    summaries = [reasoning.create_summary() for _ in range(2)]
    text = reasoning.create_text()
    summaries.append(reasoning.create_summary())

    assert [s._index for s in summaries] == [0, 1, 2]
    assert text._index == 0


def test_content_is_absent_until_a_text_part_is_opened():
    reasoning = Reasoning(_FixedIdContext(stream=True))

    reasoning.append_summary("a").close()

    assert reasoning._item.content is None


def test_set_incomplete():
    reasoning = Reasoning(_FixedIdContext(stream=True)).set_incomplete()
    assert reasoning._item.status == ItemStatus.IN_PROGRESS

    reasoning.close()
    assert reasoning._item.status == ItemStatus.INCOMPLETE


def test_summary_set_incomplete_does_not_touch_the_item():
    reasoning = Reasoning(_FixedIdContext(stream=True))

    reasoning.create_summary().set_incomplete().close()

    assert reasoning._item.status == ItemStatus.COMPLETED
