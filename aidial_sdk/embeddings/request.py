from enum import Enum
from typing import List, Literal, Optional, Union

from aidial_sdk.chat_completion.request import Attachment
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


class EmbeddingsType(str, Enum):
    SYMMETRIC = "symmetric"
    DOCUMENT = "document"
    QUERY = "query"


class EmbeddingsRequestCustomFields(ExtraForbidModel):
    type: Optional[EmbeddingsType] = None
    instruction: Optional[StrictStr] = None


EmbeddingsMultiModalInput = Union[
    StrictStr, Attachment, List[Union[StrictStr, Attachment]]
]


class EmbeddingsRequest(AzureEmbeddingsRequest):
    custom_input: Optional[List[EmbeddingsMultiModalInput]] = None
    custom_fields: Optional[EmbeddingsRequestCustomFields] = None


class Request(EmbeddingsRequest, FromRequestDeploymentMixin):
    pass
