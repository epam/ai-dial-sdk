import functools
import warnings
from enum import Enum
from http import HTTPStatus
from typing import Literal, assert_never

from fastapi import HTTPException as FastAPIException
from fastapi.responses import JSONResponse

from aidial_sdk.utils.json import remove_nones

ExceptionType = Literal["openai", "anthropic"]


class _AnthropicErrorType(Enum):
    INVALID_REQUEST = "invalid_request_error", 400
    AUTHENTICATION = "authentication_error", 401
    BILLING = "billing_error", 402
    PERMISSION = "permission_error", 403
    NOT_FOUND = "not_found_error", 404
    CONFLICT = "conflict_error", 409
    REQUEST_TOO_LARGE = "request_too_large", 413
    RATE_LIMIT = "rate_limit_error", 429
    API = "api_error", 500, 502
    TIMEOUT = "timeout_error", 504
    OVERLOADED = "overloaded_error", 529, 503

    def __init__(self, code: str, *status_codes: int) -> None:
        self.code = code
        self.status_codes = status_codes

    @classmethod
    def from_status_code(cls, status_code: int) -> "_AnthropicErrorType":
        for error_type in cls:
            if status_code in error_type.status_codes:
                return error_type
        # Anthropic answers the other 4xx statuses with invalid_request_error
        return cls.INVALID_REQUEST if 400 <= status_code < 500 else cls.API


class HTTPException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        type: str | None = "runtime_error",
        param: str | None = None,
        code: str | None = None,
        display_message: str | None = None,
        headers: dict[str, str] | None = None,
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

    def json_error(self, api: ExceptionType = "openai") -> dict:
        match api:
            case "openai":
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
            case "anthropic":
                error_type = _AnthropicErrorType.from_status_code(
                    self.status_code
                )
                return {
                    "type": "error",
                    "error": {"type": error_type.code, "message": self.message},
                }
            case _:
                assert_never(api)

    def to_fastapi_response(
        self, api: ExceptionType = "openai"
    ) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content=self.json_error(api),
            headers=self.headers,
        )

    def to_fastapi_exception(
        self, api: ExceptionType = "openai"
    ) -> FastAPIException:
        return FastAPIException(
            status_code=self.status_code,
            detail=self.json_error(api),
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
