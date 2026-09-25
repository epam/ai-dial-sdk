import pytest

from aidial_sdk.chat_completion import Choice, Status
from aidial_sdk.chat_completion._types import ChunkQueue


def test_stage_exit_with_exception_when_already_closed():
    queue = ChunkQueue()
    choice = Choice(queue, 0)
    choice.open()
    stage = choice.create_stage("test-stage")

    with pytest.raises(ValueError, match="Test exception"), stage:
        stage.close(Status.COMPLETED)
        raise ValueError("Test exception")
