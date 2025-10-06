import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Optional, Type, TypeVar
from urllib.parse import urljoin

import fastapi

from aidial_sdk._pydantic import (
    PYDANTIC_V2,
    ConfigDict,
    Field,
    SecretStr,
    StrictStr,
)
from aidial_sdk._pydantic._compat import model_validator
from aidial_sdk.exceptions import InternalServerError, InvalidRequestError
from aidial_sdk.utils.logging import log_debug
from aidial_sdk.utils.pydantic import ExtraAllowModel

T = TypeVar("T", bound="FromRequestMixin")


class FromRequestMixin(ABC, ExtraAllowModel):
    @classmethod
    @abstractmethod
    async def from_request(
        cls: Type[T],
        request: fastapi.Request,
        deployment_id: str,
        base_url: Optional[str],
    ) -> T:
        pass

    @staticmethod
    @abstractmethod
    async def get_request_body(request: fastapi.Request) -> Any:
        pass


_DIAL_APPLICATION_PROPERTIES_HEADER = "X-DIAL-APPLICATION-PROPERTIES"
_DIAL_APPLICATION_ID_HEADER = "X-DIAL-APPLICATION-ID"


class FromRequestDeploymentMixin(FromRequestMixin):

    headers: Mapping[str, str]
    base_url: Optional[str] = None
    api_key_secret: SecretStr
    jwt_secret: Optional[SecretStr] = None
    deployment_id: StrictStr
    api_version: Optional[StrictStr] = None
    unreliable_dial_application_properties: Optional[Dict[str, Any]] = None
    dial_application_id: Optional[str] = None
    original_request: fastapi.Request = Field(..., exclude=True)

    if PYDANTIC_V2:
        model_config = ConfigDict(arbitrary_types_allowed=True)
    else:

        class Config:
            arbitrary_types_allowed = True

    async def request_dial_application_properties(
        self,
    ) -> Optional[Dict[str, Any]]:
        if self.unreliable_dial_application_properties:
            return self.unreliable_dial_application_properties

        if not self.dial_application_id:
            raise InvalidRequestError(
                f"The {_DIAL_APPLICATION_ID_HEADER} header isn't set"
            )

        if not self.base_url:
            raise InternalServerError(
                "DIALApp dial_url should be set to perform request_dial_application_properties invocation"
            )

        try:
            import httpx
        except ImportError:
            raise InternalServerError(
                "Missing httpx dependencies. "
                "Install the package with the extras: aidial-sdk[httpx]"
            )

        try:
            log_debug(
                f"Requesting application properties for {self.dial_application_id!r}"
            )
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method="GET",
                    url=urljoin(
                        self.base_url,
                        f"/openai/applications/{self.dial_application_id}",
                    ),
                    headers={"api-key": self.api_key_secret.get_secret_value()},
                )
                response.raise_for_status()
                properties_dictionary = response.json().get(
                    "application_properties"
                )
                log_debug(
                    f"Received application properties for {self.dial_application_id!r}: {properties_dictionary}"
                )
                return properties_dictionary
        except Exception as ex:
            raise InternalServerError(
                f"Unable to retrieve application properties for the application {self.dial_application_id!r}: {ex}",
            )

    @model_validator(mode="before")
    @classmethod
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
    async def from_request(
        cls,
        request: fastapi.Request,
        deployment_id: StrictStr,
        base_url: Optional[str],
    ):
        headers = request.headers.mutablecopy()

        api_key = headers.get("Api-Key")
        if api_key is None:
            raise InvalidRequestError("Api-Key header is required")
        del headers["Api-Key"]

        jwt = headers.get("Authorization")
        del headers["Authorization"]

        application_properties = None
        props_header = headers.get(_DIAL_APPLICATION_PROPERTIES_HEADER)
        if props_header:
            try:
                application_properties = json.loads(props_header)
            except json.JSONDecodeError:
                raise InvalidRequestError(
                    f"The value of {_DIAL_APPLICATION_PROPERTIES_HEADER} header isn't valid JSON"
                )

        application_id = headers.get(_DIAL_APPLICATION_ID_HEADER)

        return cls(
            **(await cls.get_request_body(request)),
            api_key_secret=SecretStr(api_key),
            jwt_secret=SecretStr(jwt) if jwt else None,
            deployment_id=deployment_id,
            api_version=request.query_params.get("api-version"),
            headers=headers,
            original_request=request,
            base_url=base_url,
            unreliable_dial_application_properties=application_properties,
            dial_application_id=application_id,
        )

    @staticmethod
    async def get_request_body(request: fastapi.Request) -> dict:
        return await _get_request_json_body(request)


async def _get_request_json_body(request: fastapi.Request) -> dict:
    try:
        return await request.json()
    except json.JSONDecodeError as e:
        raise InvalidRequestError(f"The request body isn't valid JSON: {e.msg}")
