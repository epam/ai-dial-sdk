import functools
import warnings
from http import HTTPStatus
from typing import Dict, Optional

from fastapi import HTTPException as FastAPIException
from fastapi.responses import JSONResponse

from aidial_sdk.utils.json import remove_nones


class HTTPException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        type: Optional[str] = "runtime_error",
        param: Optional[str] = None,
        code: Optional[str] = None,
        display_message: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> None:
        super().__init__(message)
        status_code = int(status_code)

        self.message = message
        self.status_code = status_code
        self.type = type
        self.param = param
        self.code = code or str(status_code)
        self.display_message = display_message
        self.headers = headers
        self.extra_fields = kwargs

    def __repr__(self):
        # headers field is omitted deliberately
        # since it may contain sensitive information
        error = {
            "message": self.message,
            "status_code": self.status_code,
            "type": self.type,
            "param": self.param,
            "code": self.code,
            "display_message": self.display_message,
            **self.extra_fields,
        }
        args = ", ".join([f"{k}={v!r}" for k, v in error.items()])
        return f"{self.__class__.__name__}({args})"

    def json_error(self) -> dict:
        return {
            "error": remove_nones(
                {
                    "message": self.message,
                    "type": self.type,
                    "param": self.param,
                    "code": self.code,
                    "display_message": self.display_message,
                    **self.extra_fields,
                }
            )
        }

    def to_fastapi_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content=self.json_error(),
            headers=self.headers,
        )

    def to_fastapi_exception(self) -> FastAPIException:
        return FastAPIException(
            status_code=self.status_code,
            detail=self.json_error(),
            headers=self.headers,
        )


class ResourceNotFoundError(HTTPException):
    """
    Thrown by OpenAI when either endpoint is invalid or api-version is unknown
    """

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            status_code=HTTPStatus.NOT_FOUND,
            message=message,
            **kwargs,
        )


class DeploymentNotFoundError(HTTPException):
    """
    Thrown by OpenAI when the deployment isn't found
    """

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            status_code=HTTPStatus.NOT_FOUND,
            code="DeploymentNotFound",
            message=message,
            **kwargs,
        )


class RequestValidationError(HTTPException):
    def __init__(self, message: str, **kwargs) -> None:
        return super().__init__(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            type="invalid_request_error",
            message=message,
            **kwargs,
        )


class InvalidRequestError(HTTPException):
    def __init__(self, message: str, **kwargs) -> None:
        return super().__init__(
            status_code=HTTPStatus.BAD_REQUEST,
            type="invalid_request_error",
            message=message,
            **kwargs,
        )


class ContextLengthExceededError(InvalidRequestError):
    """
    The error message that Azure OpenAI returns when the context length is exceeded.
    """

    def __init__(self, max_context_length: int, prompt_tokens: int) -> None:
        message = (
            f"This model's maximum context length is {max_context_length} tokens. "
            f"However, your messages resulted in {prompt_tokens} tokens. "
            "Please reduce the length of the messages."
        )
        return super().__init__(
            message=message,
            code="context_length_exceeded",
            param="messages",
        )


class _TruncatePromptError(InvalidRequestError):
    def __init__(self, message: str, **kwargs) -> None:
        return super().__init__(
            message=message,
            code="truncate_prompt_error",
            param="max_prompt_tokens",
            **kwargs,
        )


class TruncatePromptSystemError(_TruncatePromptError):
    """
    The error message mimics the one of `ContextLengthExceededError`.
    """

    def __init__(self, max_prompt_tokens: int, prompt_tokens: int) -> None:
        message = (
            f"The requested maximum prompt tokens is {max_prompt_tokens}. "
            f"However, the system messages resulted in {prompt_tokens} tokens. "
            "Please reduce the length of the system messages or increase the maximum prompt tokens."
        )
        return super().__init__(message=message, display_message=message)


class TruncatePromptSystemAndLastUserError(_TruncatePromptError):
    def __init__(self, max_prompt_tokens: int, prompt_tokens: int) -> None:
        message = (
            f"The requested maximum prompt tokens is {max_prompt_tokens}. "
            f"However, the system messages and the last user message resulted in {prompt_tokens} tokens. "
            "Please reduce the length of the messages or increase the maximum prompt tokens."
        )
        return super().__init__(message=message, display_message=message)


class RuntimeServerError(HTTPException):
    def __init__(self, message: str, **kwargs) -> None:
        return super().__init__(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            type="runtime_error",
            message=message,
            **kwargs,
        )


class InternalServerError(HTTPException):
    def __init__(self, message: str, **kwargs) -> None:
        return super().__init__(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            type="internal_server_error",
            message=message,
            **kwargs,
        )


def _deprecated(ctor):
    @functools.wraps(ctor)
    def wrapped(*args, **kwargs):
        warnings.warn(
            "The helper method is deprecated. "
            f"Use {ctor.__name__} class constructor directly.",
            DeprecationWarning,
            stacklevel=2,
        )
        return ctor(*args, **kwargs)

    return wrapped


resource_not_found_error = _deprecated(ResourceNotFoundError)
deployment_not_found_error = _deprecated(DeploymentNotFoundError)
request_validation_error = _deprecated(RequestValidationError)
invalid_request_error = _deprecated(InvalidRequestError)
context_length_exceeded_error = _deprecated(ContextLengthExceededError)
truncate_prompt_error_system = _deprecated(TruncatePromptSystemError)
truncate_prompt_error_system_and_last_user = _deprecated(
    TruncatePromptSystemAndLastUserError
)
runtime_server_error = _deprecated(RuntimeServerError)
internal_server_error = _deprecated(InternalServerError)
