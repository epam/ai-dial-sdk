from typing import List, Literal, Optional, Union

from aidial_sdk._pydantic import StrictInt, StrictStr
from aidial_sdk.chat_completion.request import Attachment
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.utils.pydantic import ExtraAllowModel


class AzureEmbeddingsRequest(ExtraAllowModel):
    model: Optional[StrictStr] = None
    input: Union[
        StrictStr, List[StrictStr], List[StrictInt], List[List[StrictInt]]
    ]
    encoding_format: Literal["float", "base64"] = "float"
    dimensions: Optional[StrictInt] = None
    user: Optional[StrictStr] = None


class EmbeddingsRequestCustomFields(ExtraAllowModel):
    type: Optional[StrictStr] = None
    instruction: Optional[StrictStr] = None


EmbeddingsMultiModalInput = Union[
    StrictStr, Attachment, List[Union[StrictStr, Attachment]]
]


class EmbeddingsRequest(AzureEmbeddingsRequest):
    custom_input: Optional[List[EmbeddingsMultiModalInput]] = None
    custom_fields: Optional[EmbeddingsRequestCustomFields] = None


class Request(EmbeddingsRequest, FromRequestDeploymentMixin):
    pass
