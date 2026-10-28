from pydantic import BaseModel, ConfigDict


class ExtraForbidModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtraAllowModel(BaseModel):
    model_config = ConfigDict(extra="allow")
