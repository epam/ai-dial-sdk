import pytest

from aidial_sdk.responses.models import (
    OpenPageAction,
    SearchAction,
    SearchSource,
)
from aidial_sdk.responses.server_tool import ImageGeneration, WebSearch
from tests.responses.conftest import (
    _FixedIdContext,
    drain,
    raises_runtime_error,
)
from tests.responses.test_reference import (
    image_generation_failed,
    web_search_failed,
)


@pytest.mark.parametrize(
    "build, terminal",
    [
        (web_search_failed, "response.web_search_call.completed"),
        (image_generation_failed, "response.image_generation_call.completed"),
    ],
)
def test_failure_is_recorded_without_the_terminal_event(build, terminal: str):
    # The builder's part of a failure: the exception keeps travelling
    ctx = _FixedIdContext(stream=True)
    build(ctx)

    stream = drain(ctx)

    assert terminal not in [event["type"] for event in stream]
    assert stream[-1]["type"] == "response.output_item.done"
    assert stream[-1]["item"]["status"] == "failed"


def test_fail_closes():
    ctx = _FixedIdContext(stream=True)
    search = WebSearch(ctx)

    search._fail_self()

    assert search.closed
    assert search._item.status == "failed"


def test_action_defaults_to_search():
    search = WebSearch(_FixedIdContext(stream=True))

    assert search._item.action == SearchAction()


def test_searching_sets_the_query_and_status():
    search = WebSearch(_FixedIdContext(stream=True))

    search.searching(query="q", queries=["q1", "q2"]).add_source("u")

    assert search._item.status == "searching"
    assert search._item.action == SearchAction(
        query="q", queries=["q1", "q2"], sources=[SearchSource(url="u")]
    )


def test_partial_image_index_counts_from_zero():
    ctx = _FixedIdContext(stream=True)
    image = ImageGeneration(ctx)
    drain(ctx)

    image.append_partial("a").append_partial("b")

    assert [e["partial_image_index"] for e in drain(ctx)] == [0, 1]
    assert image._item.result is None


def _open_page_search() -> WebSearch:
    search = WebSearch(_FixedIdContext(stream=True))
    return search.set_action(OpenPageAction(url="u"))


@pytest.mark.parametrize(
    "call, reason",
    [
        (
            lambda: _open_page_search().add_source("u"),
            "add a source to a web search whose action is not a search",
        ),
        (
            lambda: _open_page_search().searching(query="q"),
            "set the query of a web search whose action is not a search",
        ),
    ],
)
def test_guard_rails(caplog, call, reason: str):
    # The web search action's rails; the others are in test_guard_rails
    with raises_runtime_error(caplog, f"Trying to {reason}"):
        call()


def test_searching_without_a_query_keeps_another_action():
    search = _open_page_search()

    search.searching()

    assert search._item.action == OpenPageAction(url="u")
