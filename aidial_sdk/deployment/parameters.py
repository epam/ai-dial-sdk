from typing import Mapping, Optional

from aidial_sdk.pydantic_v1 import StrictStr
from aidial_sdk.utils.pydantic import ExtraForbidModel


class DeploymentParameters(ExtraForbidModel):
    api_key: StrictStr
    jwt: Optional[StrictStr] = None
    deployment_id: StrictStr
    api_version: Optional[StrictStr] = None
    headers: Mapping[StrictStr, StrictStr]
