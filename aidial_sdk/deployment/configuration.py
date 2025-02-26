from json import loads, JSONDecodeError

from fastapi import Request
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.pydantic_v1 import BaseModel
from typing import Optional, Dict, Any
from aidial_sdk.exceptions import HTTPException as DIALException

class ConfigurationRequest(FromRequestDeploymentMixin):
    application_properties: Optional[Dict[str, Any]] = None

    @staticmethod
    async def get_request_body(request: Request) -> dict:
        return {}

    @classmethod
    async def from_request(cls, request: Request, deployment_id: str):
        inst = await super().from_request(request, deployment_id)
        props_header = request.headers.get("X-APPLICATION-PROPERTIES")
        try:
            if props_header:
                inst.application_properties = loads(props_header)
        except JSONDecodeError as e:
            raise DIALException(
                status_code=400,
                type="invalid_request_error",
                message=f"The application properties header isn't valid JSON: {e.msg}",
            )
        return inst


class ConfigurationResponse(BaseModel):
    class Config:
        extra = "allow"