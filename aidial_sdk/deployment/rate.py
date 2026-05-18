from aidial_sdk._pydantic import Field, StrictStr
from aidial_sdk.deployment.from_request_mixin import FromRequestDeploymentMixin


class RateRequest(FromRequestDeploymentMixin):
    response_id: StrictStr | None = Field(None, alias="responseId")
    rate: bool = False
