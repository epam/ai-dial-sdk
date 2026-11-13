import pytest


@pytest.fixture(params=[False, True], ids=["block", "stream"])
def stream(request: pytest.FixtureRequest) -> bool:
    """Runs a test with both a non-streaming and a streaming request."""
    return request.param
