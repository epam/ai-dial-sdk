from abc import ABC, abstractmethod
from json import JSONDecodeError
from typing import Any, Mapping, Optional, Type, TypeVar

import fastapi
from pydantic import Field

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.pydantic_v1 import SecretStr, StrictStr, root_validator
from aidial_sdk.utils.logging import log_debug
from aidial_sdk.utils.pydantic import ExtraForbidModel

T = TypeVar("T", bound="FromRequestMixin")


class FromRequestMixin(ABC, ExtraForbidModel):
    @classmethod
    @abstractmethod
    async def from_request(
        cls: Type[T], request: fastapi.Request, deployment_id: str
    ) -> T:
        pass


class FromRequestBasicMixin(FromRequestMixin):
    @classmethod
    async def from_request(cls, request: fastapi.Request, deployment_id: str):
        return cls(**(await _get_request_body(request)))


class FromRequestDeploymentMixin(FromRequestMixin):
    api_key_secret: SecretStr
    jwt_secret: Optional[SecretStr] = None

    deployment_id: StrictStr
    api_version: Optional[StrictStr] = None
    headers: Mapping[StrictStr, StrictStr]

    original_request: fastapi.Request = Field(..., exclude=True)

    class Config:
        arbitrary_types_allowed = True

    @root_validator(pre=True)
    def create_secrets(cls, values: dict):
        if "api_key" in values:
            if "api_key_secret" not in values:
                values["api_key_secret"] = SecretStr(values.pop("api_key"))
            else:
                raise ValueError(
                    "api_key and api_key_secret cannot be both provided"
                )

        if "jwt" in values:
            if "jwt_secret" not in values:
                values["jwt_secret"] = SecretStr(values.pop("jwt"))
            else:
                raise ValueError("jwt and jwt_secret cannot be both provided")

        return values

    @property
    def api_key(self) -> str:
        return self.api_key_secret.get_secret_value()

    @property
    def jwt(self) -> Optional[str]:
        return self.jwt_secret.get_secret_value() if self.jwt_secret else None

    @classmethod
    async def from_request(cls, request: fastapi.Request, deployment_id: str):
        headers = request.headers.mutablecopy()

        api_key = headers.get("Api-Key")
        if api_key is None:
            raise DIALException(
                status_code=400,
                type="invalid_request_error",
                message="Api-Key header is required",
            )
        del headers["Api-Key"]

        jwt = headers.get("Authorization")
        del headers["Authorization"]

        return cls(
            **(await _get_request_body(request)),
            api_key_secret=SecretStr(api_key),
            jwt_secret=SecretStr(jwt) if jwt else None,
            deployment_id=deployment_id,
            api_version=request.query_params.get("api-version"),
            headers=headers,
            original_request=request,
        )


async def _get_request_body(request: fastapi.Request) -> Any:
    try:
        body = await request.json()
        log_debug(f"request: {body}")
        return body
    except JSONDecodeError as e:
        raise DIALException(
            status_code=400,
            type="invalid_request_error",
            message=f"The request body isn't valid JSON: {e.msg}",
        )
