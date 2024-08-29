from aidial_sdk.exceptions import runtime_server_error
from aidial_sdk.utils.logging import log_error

RUNTIME_ERROR_MESSAGE = "Error during processing the request"


def runtime_error(reason: str):
    log_error(reason)
    return runtime_server_error(RUNTIME_ERROR_MESSAGE)
