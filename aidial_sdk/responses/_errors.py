from http import HTTPStatus

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.responses.enums import ErrorCode


def map_exception(exc: DIALException) -> tuple[ErrorCode, str]:
    """
    Maps a DIAL exception onto the `code` and `message` of `ResponseError`,
    the only two fields the Responses protocol allows in an error.
    """
    if exc.status_code == HTTPStatus.TOO_MANY_REQUESTS:
        code = ErrorCode.RATE_LIMIT_EXCEEDED
    elif 400 <= exc.status_code < 500:
        code = ErrorCode.INVALID_PROMPT
    else:
        code = ErrorCode.SERVER_ERROR

    return code, exc.message
