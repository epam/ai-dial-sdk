from abc import ABC, abstractmethod
from json import JSONDecodeError, loads
from typing import Any, Mapping, Optional, Type, TypeVar, Dict
from urllib.parse import urljoin

import fastapi
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.http_client import BaseHTTPClient, HttpRequestOptions
from aidial_sdk.pydantic_v1 import Field, SecretStr, StrictStr, root_validator, BaseModel
from aidial_sdk.utils.pydantic import ExtraForbidModel
from starlette.datastructures import MutableHeaders

T = TypeVar("T", bound="FromRequestMixin")


class FromRequestMixin(ABC, ExtraForbidModel):
    @classmethod
    @abstractmethod
    async def from_request(
            cls: Type[T], request: fastapi.Request, deployment_id: str, http_client: BaseHTTPClient
    ) -> T:
        pass

    @staticmethod
    @abstractmethod
    async def get_request_body(request: fastapi.Request) -> Any:
        pass


class ApplicationPropertiesMixin(ExtraForbidModel):
    application_properties: Optional[Dict[str, Any]] = None

    @staticmethod
    async def application_properties_from_headers(headers: MutableHeaders, http_client: BaseHTTPClient, api_key: str) -> \
    Optional[Dict[str, Any]]:
        props_header = headers.get("X-DIAL-APPLICATION-PROPERTIES")
        if props_header:
            try:
                return loads(props_header)
            except JSONDecodeError as e:
                raise DIALException(
                    status_code=400,
                    type="invalid_request_error",
                    message=f"The X-APPLICATION-PROPERTIES header isn't valid JSON: {e.msg}",
                )
        else:
            dial_app_id = headers.get("X-DIAL-APPLICATION-ID")
            if not dial_app_id:
                return None
            try:
                class Application(BaseModel):
                    application_properties: dict[str, Any]

                    class Config:
                        arbitrary_types_allowed = True
                        extra = "allow"

                response = await http_client.request(
                    HttpRequestOptions(method="GET", path=urljoin("/openai/applications/", dial_app_id),
                                       headers={"api-key": api_key}), cast_to=Application)
                return response.application_properties
            except Exception as e:
                raise DIALException(
                    status_code=500,
                    type="internal_server_error",
                    message=f"Error while fetching application (app_id {dial_app_id})properties: {e}",
                )


class FromRequestBasicMixin(FromRequestMixin, ApplicationPropertiesMixin):
    @classmethod
    async def from_request(cls, request: fastapi.Request, deployment_id: str, http_client: BaseHTTPClient):
        headers = request.headers.mutablecopy()
        application_properties = await cls.application_properties_from_headers(headers, http_client,
                                                                               headers.get("Api-Key"))

        return cls(
            **(await cls.get_request_body(request)),
            application_properties=application_properties
        )

    @staticmethod
    async def get_request_body(request: fastapi.Request) -> dict:
        return await _get_request_json_body(request)


class FromRequestDeploymentMixin(FromRequestMixin, ApplicationPropertiesMixin):
    api_key_secret: SecretStr
    jwt_secret: Optional[SecretStr] = None

    deployment_id: StrictStr
    api_version: Optional[StrictStr] = None
    headers: Mapping[StrictStr, StrictStr]

    original_request: fastapi.Request = Field(..., exclude=True)

    application_properties: Optional[Dict[str, Any]] = None

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
    async def from_request(cls, request: fastapi.Request, deployment_id: str, http_client: BaseHTTPClient,
                           **kwargs: Any):
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

        application_properties = await cls.application_properties_from_headers(headers, http_client, api_key)

        return cls(
            **(await cls.get_request_body(request)),
            api_key_secret=SecretStr(api_key),
            jwt_secret=SecretStr(jwt) if jwt else None,
            deployment_id=deployment_id,
            api_version=request.query_params.get("api-version"),
            headers=headers,
            original_request=request,
            application_properties=application_properties
        )

    @staticmethod
    async def get_request_body(request: fastapi.Request) -> dict:
        return await _get_request_json_body(request)


async def _get_request_json_body(request: fastapi.Request) -> dict:
    try:
        return await request.json()
    except JSONDecodeError as e:
        raise DIALException(
            status_code=400,
            type="invalid_request_error",
            message=f"The request body isn't valid JSON: {e.msg}",
        )
