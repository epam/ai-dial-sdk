from enum import Enum
from typing import List, Literal, Optional, Union

from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
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


class EmbeddingsRequestCustomFields(ExtraForbidModel):
    type: Optional[DialEmbeddingsType] = None
    instruction: Optional[StrictStr] = None


class EmbeddingsRequest(AzureEmbeddingsRequest):
    custom_fields: Optional[EmbeddingsRequestCustomFields] = None


class Request(EmbeddingsRequest, FromRequestDeploymentMixin):
    pass
