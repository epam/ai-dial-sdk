import warnings
from abc import ABC, abstractmethod
from json import JSONDecodeError
from typing import Any, Mapping, Optional, Type, TypeVar

import fastapi
from deprecated import deprecated

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.pydantic_v1 import SecretStr, StrictStr, root_validator
from aidial_sdk.utils.logging import log_debug
from aidial_sdk.utils.pydantic import ExtraForbidModel

T = TypeVar("T", bound="FromRequestMixin")


class FromRequestMixin(ABC, ExtraForbidModel):
    @classmethod
    @abstractmethod
    async def from_request(cls: Type[T], request: fastapi.Request) -> T:
        pass


class FromRequestBasicMixin(FromRequestMixin):
    @classmethod
    async def from_request(cls, request: fastapi.Request):
        return cls(**(await _get_request_body(request)))


class FromRequestDeploymentMixin(FromRequestMixin):
    api_key_secret: SecretStr
    jwt_secret: Optional[SecretStr] = None

    deployment_id: StrictStr
    api_version: Optional[StrictStr] = None
    headers: Mapping[StrictStr, StrictStr]

    @root_validator(pre=True)
    def check_deprecated_fields(cls, values: dict):
        if "api_key" in values:
            warnings.warn(
                "The 'api_key' property is deprecated. "
                "Use 'api_key_secret' instead.",
                DeprecationWarning,
                stacklevel=4,
            )
            if "api_key_secret" not in values:
                values["api_key_secret"] = SecretStr(values.pop("api_key"))

        if "jwt" in values:
            warnings.warn(
                "The 'jwt' property is deprecated. "
                "Use 'jwt_secret' instead.",
                DeprecationWarning,
                stacklevel=4,
            )
            if "jwt_secret" not in values:
                values["jwt_secret"] = SecretStr(values.pop("jwt"))

        return values

    @property
    @deprecated(reason="Use 'api_key_secret' property instead")
    def api_key(self) -> str:
        return self.api_key_secret.get_secret_value()

    @property
    @deprecated(reason="Use 'jwt_secret' property instead")
    def jwt(self) -> Optional[str]:
        return self.jwt_secret.get_secret_value() if self.jwt_secret else None

    @classmethod
    async def from_request(cls, request: fastapi.Request):
        deployment_id = request.path_params.get("deployment_id")
        if deployment_id is None or not isinstance(deployment_id, str):
            raise DIALException(
                status_code=404,
                type="invalid_path",
                message="Invalid path",
            )

        headers = request.headers
        api_key = headers.get("Api-Key")
        if api_key is None:
            raise DIALException(
                status_code=400,
                type="invalid_request_error",
                message="Api-Key header is required",
            )

        jwt = headers.get("Authorization")

        return cls(
            **(await _get_request_body(request)),
            api_key_secret=SecretStr(api_key),
            jwt_secret=SecretStr(jwt) if jwt else None,
            deployment_id=deployment_id,
            api_version=request.query_params.get("api-version"),
            headers=headers,
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
            message=f"Your request contained invalid JSON: {e.msg}",
        )
