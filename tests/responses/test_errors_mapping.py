import logging

import pytest

from aidial_sdk._errors import INTERNAL_ERROR_MESSAGE, to_dial_exception
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.exceptions import (
    InternalServerError,
    InvalidRequestError,
    RuntimeServerError,
)
from aidial_sdk.responses._errors import map_exception
from aidial_sdk.responses.enums import ErrorCode


def test_429_is_rate_limit_exceeded():
    exc = DIALException("Too many requests", status_code=429)
    assert map_exception(exc) == (
        ErrorCode.RATE_LIMIT_EXCEEDED,
        "Too many requests",
    )


@pytest.mark.parametrize("status_code", [400, 401, 404, 422, 499])
def test_other_4xx_is_invalid_prompt(status_code: int):
    exc = DIALException("Bad prompt", status_code=status_code)
    assert map_exception(exc) == (ErrorCode.INVALID_PROMPT, "Bad prompt")


@pytest.mark.parametrize("status_code", [500, 502, 503, 599])
def test_5xx_is_server_error(status_code: int):
    exc = DIALException("Upstream failed", status_code=status_code)
    assert map_exception(exc) == (ErrorCode.SERVER_ERROR, "Upstream failed")


def test_dial_exception_subclasses():
    assert map_exception(InvalidRequestError("Invalid")) == (
        ErrorCode.INVALID_PROMPT,
        "Invalid",
    )
    assert map_exception(RuntimeServerError("Runtime")) == (
        ErrorCode.SERVER_ERROR,
        "Runtime",
    )


def test_only_the_message_survives():
    exc = DIALException(
        "Message",
        status_code=400,
        type="custom_type",
        param="custom_param",
        code="custom_code",
        display_message="Display message",
    )
    assert map_exception(exc) == (ErrorCode.INVALID_PROMPT, "Message")


def test_dial_exception_is_kept():
    exc = DIALException("Too many requests", status_code=429)
    assert to_dial_exception(exc) is exc


def test_non_dial_exception_does_not_leak(caplog: pytest.LogCaptureFixture):
    original_message = "leaked-api-key-123"

    # Called while the exception is handled, as the response does
    with caplog.at_level(logging.ERROR, logger="aidial_sdk"):
        try:
            raise ValueError(original_message)
        except ValueError as e:
            exc = to_dial_exception(e)
        code, message = map_exception(exc)

    assert isinstance(exc, InternalServerError)
    assert code == ErrorCode.SERVER_ERROR
    assert message == INTERNAL_ERROR_MESSAGE
    assert original_message not in message

    # the original is logged, with the traceback
    (record,) = caplog.records
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], ValueError)
    assert original_message in str(record.exc_info[1])
