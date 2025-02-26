from pydantic import Field, StrictStr

from aidial_sdk.deployment.from_request_mixin import FromRequestBasicMixin


class RateRequest(FromRequestBasicMixin):
    response_id: StrictStr = Field(None, alias="responseId")
    rate: bool = False
