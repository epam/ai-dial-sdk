from typing import Literal

from aidial_sdk._pydantic import StrictInt, StrictStr
from aidial_sdk.chat_completion.request import Attachment
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.utils.pydantic import ExtraAllowModel


class AzureEmbeddingsRequest(ExtraAllowModel):
    model: StrictStr | None = None
    input: StrictStr | list[StrictStr] | list[StrictInt] | list[list[StrictInt]]
    encoding_format: Literal["float", "base64"] = "float"
    dimensions: StrictInt | None = None
    user: StrictStr | None = None


class EmbeddingsRequestCustomFields(ExtraAllowModel):
    type: StrictStr | None = None
    instruction: StrictStr | None = None


EmbeddingsMultiModalInput = (
    StrictStr | Attachment | list[StrictStr | Attachment]
)


class EmbeddingsRequest(AzureEmbeddingsRequest):
    custom_input: list[EmbeddingsMultiModalInput] | None = None
    custom_fields: EmbeddingsRequestCustomFields | None = None


class Request(EmbeddingsRequest, FromRequestDeploymentMixin):
    pass
