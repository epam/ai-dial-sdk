from aidial_sdk._pydantic import PYDANTIC_V2, ConfigDict
from aidial_sdk._pydantic._compat import BaseModel


class ExtraForbidModel(BaseModel):
    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")
    else:

        class Config:
            extra = "forbid"


class ExtraAllowModel(BaseModel):
    if PYDANTIC_V2:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"
