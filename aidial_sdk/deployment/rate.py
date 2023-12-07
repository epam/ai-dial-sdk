from aidial_sdk.deployment.from_request_mixin import FromRequestBasicMixin
from aidial_sdk.pydantic_v1 import Field, StrictStr


class RateRequest(FromRequestBasicMixin):
    response_id: StrictStr = Field(None, alias="responseId")
    rate: bool = False
