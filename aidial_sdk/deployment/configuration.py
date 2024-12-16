import fastapi

from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.pydantic_v1 import BaseModel


class ConfigurationRequest(FromRequestDeploymentMixin):
    @staticmethod
    async def get_request_body(request: fastapi.Request) -> dict:
        return {}


class ConfigurationResponse(BaseModel):
    class Config:
        extra = "allow"
