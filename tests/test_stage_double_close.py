import pytest

from aidial_sdk.chat_completion import Status
from aidial_sdk.chat_completion._types import ChunkQueue
from aidial_sdk.chat_completion.stage import Stage


def test_stage_exit_with_exception_when_already_closed():
    queue = ChunkQueue()
    stage = Stage(queue, choice_index=0, stage_index=0, name="test-stage")

    with pytest.raises(ValueError, match="Test exception"):
        with stage:
            stage.close(Status.COMPLETED)
            raise ValueError("Test exception")
