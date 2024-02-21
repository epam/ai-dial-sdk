from typing import Optional

from aidial_sdk.exceptions import HTTPException
from aidial_sdk.utils.json import remove_nones
from aidial_sdk.utils.logging import log_error


def runtime_error(reason: str):
    log_error(reason)

    return HTTPException(
        status_code=500,
        message="Error during processing the request",
        type="runtime_error",
    )


def json_error(
    message: Optional[str] = None,
    type: Optional[str] = None,
    param: Optional[str] = None,
    code: Optional[str] = None,
    display_message: Optional[str] = None,
):
    return {
        "error": remove_nones(
            {
                "message": message,
                "type": type,
                "param": param,
                "code": code,
                "display_message": display_message,
            }
        )
    }
