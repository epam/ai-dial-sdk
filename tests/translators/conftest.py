import pytest

from aidial_sdk._pydantic import PYDANTIC_V2

# The translators refuse to import without Pydantic v2
collect_ignore = (
    []
    if PYDANTIC_V2
    else ["messages_to_chat_completions", "messages_to_responses"]
)


@pytest.fixture(params=[False, True], ids=["block", "stream"])
def stream(request: pytest.FixtureRequest) -> bool:
    """Runs a test with both a non-streaming and a streaming request."""
    return request.param
