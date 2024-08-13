from http import HTTPStatus
from typing import Optional


class HTTPException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        type: Optional[str] = "runtime_error",
        param: Optional[str] = None,
        code: Optional[str] = None,
        display_message: Optional[str] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.type = type
        self.param = param
        self.code = code
        self.display_message = display_message

    def __repr__(self):
        return (
            "%s(message=%r, status_code=%r, type=%r, param=%r, code=%r, display_message=%r)"
            % (
                self.__class__.__name__,
                self.message,
                self.status_code,
                self.type,
                self.param,
                self.code,
                self.display_message,
            )
        )


def resource_not_found_error(message: str, **kwargs) -> HTTPException:
    """
    Thrown by OpenAI when either endpoint is invalid or api-version is unknown
    """
    return HTTPException(
        status_code=HTTPStatus.NOT_FOUND,
        message=message,
        **kwargs,
    )


def deployment_not_found_error(message: str, **kwargs) -> HTTPException:
    """
    Thrown by OpenAI when the deployment isn't found
    """
    return HTTPException(
        status_code=HTTPStatus.NOT_FOUND,
        code="DeploymentNotFound",
        message=message,
        **kwargs,
    )


def request_validation_error(message: str, **kwargs) -> HTTPException:
    return HTTPException(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        type="invalid_request_error",
        message=message,
        **kwargs,
    )


def invalid_request_error(message: str, **kwargs) -> HTTPException:
    return HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        type="invalid_request_error",
        message=message,
        **kwargs,
    )


def context_length_exceeded_error(
    max_context_length: int, prompt_tokens: int
) -> HTTPException:
    """
    The error message that Azure OpenAI returns when the context length is exceeded.
    """
    message = (
        f"This model's maximum context length is {max_context_length} tokens. "
        f"However, your messages resulted in {prompt_tokens} tokens. "
        "Please reduce the length of the messages."
    )
    return invalid_request_error(
        message=message,
        code="context_length_exceeded",
        param="messages",
    )


def _truncate_prompt_error(message: str, **kwargs) -> HTTPException:
    return invalid_request_error(
        code="truncate_prompt_error",
        param="max_prompt_tokens",
        message=message,
        **kwargs,
    )


def truncate_prompt_error_system(
    max_prompt_tokens: int, prompt_tokens: int
) -> HTTPException:
    """
    The error message mimics the one of `context_length_exceeded_error`.
    """
    message = (
        f"The requested maximum prompt tokens is {max_prompt_tokens}. "
        f"However, the system messages resulted in {prompt_tokens} tokens. "
        "Please reduce the length of the system messages or increase the maximum prompt tokens."
    )
    return _truncate_prompt_error(message=message, display_message=message)


def truncate_prompt_error_system_and_last_user(
    max_prompt_tokens: int, prompt_tokens: int
) -> HTTPException:
    message = (
        f"The requested maximum prompt tokens is {max_prompt_tokens}. "
        f"However, the system messages and the last user message resulted in {prompt_tokens} tokens. "
        "Please reduce the length of the messages or increase the maximum prompt tokens."
    )
    return _truncate_prompt_error(message=message, display_message=message)


def runtime_server_error(message: str, **kwargs) -> HTTPException:
    return HTTPException(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        type="runtime_error",
        message=message,
        **kwargs,
    )


def internal_server_error(message: str, **kwargs) -> HTTPException:
    return HTTPException(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        type="internal_server_error",
        message=message,
        **kwargs,
    )
