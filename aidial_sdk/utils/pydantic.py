from aidial_sdk.pydantic_v1 import BaseModel


class ExtraAllowModel(BaseModel):
    class Config:
        extra = "allow"
