from aidial_sdk.pydantic_v1 import BaseModel


class ExtraForbidModel(BaseModel):
    class Config:
        extra = "forbid"
