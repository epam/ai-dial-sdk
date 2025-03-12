from fastapi import Request

from aidial_sdk.deployment.application_properties_mixin import SchemaRichApplicationsMixin
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.pydantic_v1 import BaseModel
from typing import Optional, Dict, Any

class ConfigurationRequest(FromRequestDeploymentMixin, SchemaRichApplicationsMixin):

    @staticmethod
    async def get_request_body(request: Request) -> dict:
        return {}

class ConfigurationResponse(BaseModel):
    class Config:
        extra = "allow"