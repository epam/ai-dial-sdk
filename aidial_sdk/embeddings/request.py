from enum import Enum
from typing import List, Literal, Optional, Union

from fastapi import Request as FastAPIRequest

from aidial_sdk.deployment.from_request_mixin import (
    DeploymentRequest,
    FromRequestMixin,
    get_api_key,
    get_deployment_id,
    get_request_body,
)
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.pydantic_v1 import StrictFloat, StrictInt, StrictStr
from aidial_sdk.utils.pydantic import ExtraForbidModel


class AzureEmbeddingsRequest(ExtraForbidModel):
    model: Optional[StrictStr] = None
    input: Union[
        StrictStr, List[StrictStr], List[StrictFloat], List[List[StrictFloat]]
    ]
    encoding_format: Literal["float", "base64"] = "float"
    dimensions: Optional[StrictInt] = None
    user: Optional[StrictStr] = None


class DialEmbeddingsType(str, Enum):
    SYMMETRIC = "symmetric"
    DOCUMENT = "document"
    QUERY = "query"

    @classmethod
    def parse(cls, value: Optional[str]) -> Optional["DialEmbeddingsType"]:
        if value is None:
            return None
        try:
            return DialEmbeddingsType(value)
        except ValueError:
            valid_values = [e.value for e in DialEmbeddingsType]
            raise DIALException(
                status_code=400,
                type="invalid_request_error",
                message=f"Invalid value {value!r} for 'X-DIAL-Type' header. "
                f"Valid values are: {valid_values}",
            )


class EmbeddingsRequest(
    AzureEmbeddingsRequest, DeploymentRequest, FromRequestMixin
):
    embeddings_instruction: Optional[StrictStr] = None
    embeddings_type: Optional[DialEmbeddingsType] = None

    @classmethod
    async def from_request(cls, request: FastAPIRequest):
        headers = request.headers
        return cls(
            **(await get_request_body(request)),
            api_key=get_api_key(request),
            jwt=headers.get("Authorization"),
            deployment_id=get_deployment_id(request),
            api_version=request.query_params.get("api-version"),
            headers=headers,
            embeddings_instruction=headers.get("X-DIAL-Instruction"),
            embeddings_type=DialEmbeddingsType.parse(
                headers.get("X-DIAL-Type")
            ),
        )


Request = AzureEmbeddingsRequest
