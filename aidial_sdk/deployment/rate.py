from aidial_sdk.pydantic_v1 import Field, StrictStr
from aidial_sdk.utils.pydantic import ExtraForbidModel


class RateRequest(ExtraForbidModel):
    response_id: StrictStr = Field(None, alias="responseId")
    rate: bool = False
