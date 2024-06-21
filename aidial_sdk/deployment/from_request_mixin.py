from abc import ABC, abstractmethod
from json import JSONDecodeError
from typing import Any, Mapping, Optional, Type, TypeVar

from fastapi import Request

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.pydantic_v1 import StrictStr
from aidial_sdk.utils.logging import log_debug
from aidial_sdk.utils.pydantic import ExtraForbidModel

T = TypeVar("T", bound="FromRequestMixin")


class FromRequestMixin(ABC, ExtraForbidModel):
    @classmethod
    @abstractmethod
    async def from_request(cls: Type[T], request: Request) -> T:
        pass


class FromRequestBasicMixin(FromRequestMixin):
    @classmethod
    async def from_request(cls, request: Request):
        return cls(**(await get_request_body(request)))


def get_deployment_id(request: Request) -> str:
    deployment_id = request.path_params.get("deployment_id")
    if deployment_id is None or not isinstance(deployment_id, str):
        raise DIALException(
            status_code=404,
            type="invalid_path",
            message="Invalid path",
        )
    return deployment_id


def get_api_key(request: Request) -> str:
    headers = request.headers
    api_key = headers.get("Api-Key")
    if api_key is None:
        raise DIALException(
            status_code=400,
            type="invalid_request_error",
            message="Api-Key header is required",
        )
    return api_key


class DeploymentRequest(ExtraForbidModel):
    api_key: StrictStr
    jwt: Optional[StrictStr] = None
    deployment_id: StrictStr
    api_version: Optional[StrictStr] = None
    headers: Mapping[StrictStr, StrictStr]


class FromRequestDeploymentMixin(DeploymentRequest, FromRequestMixin):
    @classmethod
    async def from_request(cls, request: Request):
        return cls(
            **(await get_request_body(request)),
            api_key=get_api_key(request),
            jwt=request.headers.get("Authorization"),
            deployment_id=get_deployment_id(request),
            api_version=request.query_params.get("api-version"),
            headers=request.headers,
        )


async def get_request_body(request: Request) -> Any:
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
