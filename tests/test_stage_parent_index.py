"""Tests for parent_stage_index in StartStageChunk, Stage.stage_index, and Choice.create_stage(parent=...)."""

import asyncio

from aidial_sdk.chat_completion import Choice
from aidial_sdk.chat_completion.chunks import StartStageChunk


def _drain(queue: asyncio.Queue) -> list:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def _stage_dicts_from_queue(queue: asyncio.Queue) -> list:
    results = []
    for item in _drain(queue):
        d = item.to_dict()
        for ch in d.get("choices", []):
            for s in ch.get("delta", {}).get("custom_content", {}).get("stages", []):
                results.append(s)
    return results


class TestStartStageChunkParentIndex:
    def test_omits_parent_stage_index_when_none(self):
        chunk = StartStageChunk(choice_index=0, stage_index=0, name="step")
        d = chunk.to_dict()
        stage = d["choices"][0]["delta"]["custom_content"]["stages"][0]
        assert "parent_stage_index" not in stage

    def test_includes_parent_stage_index_when_set(self):
        chunk = StartStageChunk(
            choice_index=0, stage_index=1, name="child", parent_stage_index=0
        )
        d = chunk.to_dict()
        stage = d["choices"][0]["delta"]["custom_content"]["stages"][0]
        assert stage["parent_stage_index"] == 0

    def test_status_always_none_in_start_chunk(self):
        chunk = StartStageChunk(
            choice_index=0, stage_index=0, name="x", parent_stage_index=5
        )
        d = chunk.to_dict()
        stage = d["choices"][0]["delta"]["custom_content"]["stages"][0]
        assert stage["status"] is None

    def test_existing_fields_unchanged(self):
        chunk = StartStageChunk(choice_index=0, stage_index=3, name="foo")
        d = chunk.to_dict()
        stage = d["choices"][0]["delta"]["custom_content"]["stages"][0]
        assert stage["index"] == 3
        assert stage["name"] == "foo"
        assert stage["status"] is None


class TestStageIndex:
    def test_stage_index_property_returns_correct_value(self):
        choice = Choice(asyncio.Queue(), 0)
        choice.open()
        s0 = choice.create_stage("first")
        s1 = choice.create_stage("second")
        assert s0.stage_index == 0
        assert s1.stage_index == 1

    def test_stage_index_matches_allocation_order(self):
        choice = Choice(asyncio.Queue(), 0)
        choice.open()
        stages = [choice.create_stage(f"s{i}") for i in range(5)]
        for i, stage in enumerate(stages):
            assert stage.stage_index == i


class TestCreateStageWithParent:
    def test_create_stage_without_parent_emits_no_parent_stage_index(self):
        q = asyncio.Queue()
        choice = Choice(q, 0)
        choice.open()
        _drain(q)  # discard StartChoiceChunk
        stage = choice.create_stage("root")
        stage.open()
        stage_dicts = _stage_dicts_from_queue(q)
        root_start = next(s for s in stage_dicts if s.get("index") == 0)
        assert "parent_stage_index" not in root_start

    def test_create_stage_with_parent_emits_parent_stage_index(self):
        q = asyncio.Queue()
        choice = Choice(q, 0)
        choice.open()
        _drain(q)
        parent = choice.create_stage("parent")
        parent.open()
        child = choice.create_stage("child", parent=parent)
        child.open()
        stage_dicts = _stage_dicts_from_queue(q)
        child_start = next(s for s in stage_dicts if s.get("index") == 1)
        assert child_start["parent_stage_index"] == 0

    def test_parent_stage_index_references_parent_index(self):
        """When parent has index N, child's parent_stage_index must equal N."""
        q = asyncio.Queue()
        choice = Choice(q, 0)
        choice.open()
        _drain(q)
        choice.create_stage("skipped")           # index 0
        parent = choice.create_stage("parent")   # index 1
        parent.open()
        child = choice.create_stage("child", parent=parent)  # index 2
        child.open()
        stage_dicts = _stage_dicts_from_queue(q)
        child_start = next(s for s in stage_dicts if s.get("index") == 2)
        assert child_start["parent_stage_index"] == 1

    def test_stage_open_emits_parent_stage_index_in_wire_format(self):
        """End-to-end: opening a child stage produces correct wire-format dict."""
        q = asyncio.Queue()
        choice = Choice(q, 0)
        choice.open()
        _drain(q)
        parent = choice.create_stage("parent")
        parent.open()
        child = choice.create_stage("child", parent=parent)
        child.open()
        chunks = _drain(q)
        # Find the StartStageChunk for child (index=1)
        start_dicts = []
        for chunk in chunks:
            d = chunk.to_dict()
            for ch in d.get("choices", []):
                for s in ch.get("delta", {}).get("custom_content", {}).get("stages", []):
                    if s.get("index") == 1 and s.get("status") is None and "name" in s:
                        start_dicts.append(s)
        assert len(start_dicts) == 1
        assert start_dicts[0]["parent_stage_index"] == 0
