from typing import Mapping, Optional

from fastapi import Request

from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.pydantic_v1 import StrictStr
from aidial_sdk.utils.fastapi import get_request_body
from aidial_sdk.utils.pydantic import ExtraForbidModel


class DeploymentParametersMixin(ExtraForbidModel):
    api_key: StrictStr
    jwt: Optional[StrictStr] = None
    deployment_id: StrictStr
    api_version: Optional[StrictStr] = None
    headers: Mapping[StrictStr, StrictStr]

    @classmethod
    async def from_request(cls, request: Request):
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

        return cls(
            **(await get_request_body(request)),
            api_key=api_key,
            jwt=headers.get("Authorization"),
            deployment_id=deployment_id,
            api_version=request.query_params.get("api-version"),
            headers=headers,
        )
