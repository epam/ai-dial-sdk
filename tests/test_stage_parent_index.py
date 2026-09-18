"""Tests for nested stages.

Covers the wire format of ``parent_stage_index``, the ``Choice.create_stage``
parent parameter, the validation rules around the parent lifecycle and the
request-side model which has to accept the field back in the history.
"""

import asyncio
from unittest.mock import patch

import pytest

from aidial_sdk.chat_completion import Choice, RequestStage, Status
from aidial_sdk.chat_completion.chunks import StartStageChunk
from aidial_sdk.exceptions import RuntimeServerError
from tests.utils.pydantic import model_parse


def _drain(queue: asyncio.Queue) -> list:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def _start_stages(queue: asyncio.Queue) -> dict[int, dict]:
    """Map stage index to the stage payload of every StartStageChunk."""
    result = {}
    for item in _drain(queue):
        if not isinstance(item, StartStageChunk):
            continue
        stage = item.to_dict()["choices"][0]["delta"]["custom_content"][
            "stages"
        ][0]
        result[stage["index"]] = stage
    return result


def _opened_choice() -> tuple[Choice, asyncio.Queue]:
    queue = asyncio.Queue()
    choice = Choice(queue, 0)
    choice.open()
    _drain(queue)  # discard StartChoiceChunk
    return choice, queue


class TestStartStageChunkWireFormat:
    def test_omits_parent_stage_index_when_none(self):
        chunk = StartStageChunk(choice_index=0, stage_index=0, name="step")
        stage = chunk.to_dict()["choices"][0]["delta"]["custom_content"][
            "stages"
        ][0]
        assert "parent_stage_index" not in stage

    def test_includes_parent_stage_index_when_set(self):
        chunk = StartStageChunk(
            choice_index=0, stage_index=1, name="child", parent_stage_index=0
        )
        stage = chunk.to_dict()["choices"][0]["delta"]["custom_content"][
            "stages"
        ][0]
        assert stage["parent_stage_index"] == 0

    def test_other_fields_are_unchanged(self):
        chunk = StartStageChunk(
            choice_index=0, stage_index=3, name="foo", parent_stage_index=1
        )
        stage = chunk.to_dict()["choices"][0]["delta"]["custom_content"][
            "stages"
        ][0]
        assert stage["index"] == 3
        assert stage["name"] == "foo"
        assert stage["status"] is None


class TestStageProperties:
    def test_stage_index_follows_allocation_order(self):
        choice, _ = _opened_choice()
        stages = [choice.create_stage(f"s{i}") for i in range(5)]
        assert [stage.stage_index for stage in stages] == [0, 1, 2, 3, 4]

    def test_opened_and_closed_track_the_lifecycle(self):
        choice, _ = _opened_choice()
        stage = choice.create_stage("step")
        assert not stage.opened
        assert not stage.closed

        stage.open()
        assert stage.opened
        assert not stage.closed

        stage.close()
        assert stage.opened
        assert stage.closed


class TestCreateStageWithParent:
    def test_root_stage_emits_no_parent_stage_index(self):
        choice, queue = _opened_choice()
        choice.create_stage("root").open()
        assert "parent_stage_index" not in _start_stages(queue)[0]

    def test_child_stage_references_the_parent_index(self):
        choice, queue = _opened_choice()
        choice.create_stage("skipped")  # index 0, never opened
        parent = choice.create_stage("parent")  # index 1
        parent.open()
        choice.create_stage("child", parent=parent).open()  # index 2

        stages = _start_stages(queue)
        assert "parent_stage_index" not in stages[1]
        assert stages[2]["parent_stage_index"] == 1

    def test_nesting_is_not_limited_in_depth(self):
        choice, queue = _opened_choice()
        parent = choice.create_stage("level-0")
        parent.open()
        for level in range(1, 4):
            child = choice.create_stage(f"level-{level}", parent=parent)
            child.open()
            parent = child

        stages = _start_stages(queue)
        assert stages[1]["parent_stage_index"] == 0
        assert stages[2]["parent_stage_index"] == 1
        assert stages[3]["parent_stage_index"] == 2

    def test_siblings_share_the_same_parent(self):
        choice, queue = _opened_choice()
        parent = choice.create_stage("parent")
        parent.open()
        choice.create_stage("first", parent=parent).open()
        choice.create_stage("second", parent=parent).open()

        stages = _start_stages(queue)
        assert stages[1]["parent_stage_index"] == 0
        assert stages[2]["parent_stage_index"] == 0

    def test_parent_may_be_opened_after_the_child_is_created(self):
        choice, queue = _opened_choice()
        parent = choice.create_stage("parent")
        child = choice.create_stage("child", parent=parent)
        parent.open()
        child.open()

        assert _start_stages(queue)[1]["parent_stage_index"] == 0


class TestParentValidation:
    def test_parent_from_another_choice_is_rejected(self):
        queue = asyncio.Queue()
        first = Choice(queue, 0)
        first.open()
        second = Choice(queue, 1)
        second.open()
        foreign_parent = first.create_stage("parent")
        foreign_parent.open()

        with pytest.raises(RuntimeServerError):
            second.create_stage("child", parent=foreign_parent)

    def test_rejected_parent_does_not_consume_a_stage_index(self):
        queue = asyncio.Queue()
        first = Choice(queue, 0)
        first.open()
        second = Choice(queue, 1)
        second.open()
        foreign_parent = first.create_stage("parent")

        with pytest.raises(RuntimeServerError):
            second.create_stage("child", parent=foreign_parent)

        assert second.create_stage("next").stage_index == 0

    def test_opening_a_child_of_an_unopened_parent_is_rejected(self):
        choice, _ = _opened_choice()
        parent = choice.create_stage("parent")
        child = choice.create_stage("child", parent=parent)

        with pytest.raises(RuntimeServerError):
            child.open()

    def test_opening_a_child_of_a_closed_parent_is_rejected(self):
        choice, _ = _opened_choice()
        parent = choice.create_stage("parent")
        parent.open()
        parent.close()
        child = choice.create_stage("child", parent=parent)

        with pytest.raises(RuntimeServerError):
            child.open()


class TestClosingParentWithOpenChildren:
    def test_warns_when_a_child_is_still_open(self):
        choice, _ = _opened_choice()
        parent = choice.create_stage("parent")
        parent.open()
        choice.create_stage("child", parent=parent).open()

        with patch(
            "aidial_sdk.chat_completion.stage.log_warning"
        ) as log_warning:
            parent.close()

        assert log_warning.call_count == 1
        assert "child stages: [1]" in log_warning.call_args.args[0]

    def test_does_not_warn_when_children_are_closed_first(self):
        choice, _ = _opened_choice()
        parent = choice.create_stage("parent")
        parent.open()
        child = choice.create_stage("child", parent=parent)
        child.open()
        child.close()

        with patch(
            "aidial_sdk.chat_completion.stage.log_warning"
        ) as log_warning:
            parent.close()

        log_warning.assert_not_called()

    def test_does_not_warn_about_children_which_were_never_opened(self):
        choice, _ = _opened_choice()
        parent = choice.create_stage("parent")
        parent.open()
        choice.create_stage("child", parent=parent)

        with patch(
            "aidial_sdk.chat_completion.stage.log_warning"
        ) as log_warning:
            parent.close()

        log_warning.assert_not_called()

    def test_closing_the_parent_still_emits_the_finish_chunk(self):
        choice, queue = _opened_choice()
        parent = choice.create_stage("parent")
        parent.open()
        choice.create_stage("child", parent=parent).open()
        parent.close(Status.FAILED)

        statuses = [
            stage["status"]
            for item in _drain(queue)
            for stage in item.to_dict()["choices"][0]["delta"][
                "custom_content"
            ]["stages"]
            if stage["index"] == 0
        ]
        assert statuses[-1] == "failed"


class TestRequestStage:
    def test_accepts_parent_stage_index_under_strict_validation(self):
        stage = model_parse(
            RequestStage,
            {
                "index": 1,
                "name": "Fetching forecast",
                "status": "completed",
                "parent_stage_index": 0,
            },
            allow_extra_fields=False,
        )
        assert stage.parent_stage_index == 0

    def test_parent_stage_index_defaults_to_none(self):
        stage = model_parse(
            RequestStage,
            {"name": "Calling WeatherApp", "status": "completed"},
            allow_extra_fields=False,
        )
        assert stage.parent_stage_index is None
