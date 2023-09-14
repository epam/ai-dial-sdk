from logging import Logger

from aidial_sdk.exceptions import HTTPException


def runtime_error(log: Logger, reason: str):
    log.error(reason)

    raise HTTPException(
        status_code=500,
        message="Error during processing the request",
        type="runtime_error",
    )
