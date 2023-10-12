import pytest

from aidial_sdk import HTTPException
from aidial_sdk.chat_completion import Request, Response


def test_discarded_messages_is_set_twice():
    request = Request(headers={}, api_key="", deployment_id="", messages=[])
    response = Response(request)

    with response.create_single_choice():
        pass

    response.set_discarded_messages(1)

    with pytest.raises(HTTPException):
        response.set_discarded_messages(1)


def test_discarded_messages_is_set_before_choice():
    request = Request(headers={}, api_key="", deployment_id="", messages=[])
    response = Response(request)

    with pytest.raises(HTTPException):
        response.set_discarded_messages(1)
