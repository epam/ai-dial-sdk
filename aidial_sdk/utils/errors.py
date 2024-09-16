from aidial_sdk.exceptions import RuntimeServerError
from aidial_sdk.utils.logging import log_error

RUNTIME_ERROR_MESSAGE = "Error during processing the request"


def runtime_error(reason: str):
    log_error(reason)
    return RuntimeServerError(RUNTIME_ERROR_MESSAGE)
