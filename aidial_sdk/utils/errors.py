from logging import Logger
from typing import Optional

from aidial_sdk.exceptions import HTTPException


def runtime_error(log: Logger, reason: str):
    log.error(reason)

    raise HTTPException(
        status_code=500,
        message="Error during processing the request",
        type="runtime_error",
    )


def json_error(
    message: Optional[str] = None,
    type: Optional[str] = None,
    param: Optional[str] = None,
    code: Optional[str] = None,
):
    return {
        "error": {
            "message": message,
            "type": type,
            "param": param,
            "code": code,
        }
    }
