from aidial_sdk.deployment.application_properties_mixin import SchemaRichApplicationsMixin
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin
from aidial_sdk.pydantic_v1 import Field, StrictStr


class RateRequest(FromRequestDeploymentMixin, SchemaRichApplicationsMixin):
    response_id: StrictStr = Field(None, alias="responseId")
    rate: bool = False
