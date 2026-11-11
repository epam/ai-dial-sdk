import pytest

from aidial_sdk.responses.base import Responses
from aidial_sdk.responses.request import Request
from aidial_sdk.responses.response import Response
from tests.responses.conftest import run_response


def test_create_response_is_abstract():
    class Incomplete(Responses):
        pass

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore


async def test_subclass_runs_as_the_handler():
    class Echo(Responses):
        async def create_response(
            self, request: Request, response: Response
        ) -> None:
            response.append_text(request.messages[-1].text())

    run = await run_response(Echo().create_response, input="Hello")

    assert run.body["output"][0]["content"][0]["text"] == "Hello"
