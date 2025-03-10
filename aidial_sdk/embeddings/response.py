from typing import List, Literal, Union

from aidial_sdk.utils.pydantic import ExtraAllowModel as BaseModel


class Embedding(BaseModel):
    embedding: Union[str, List[float]]
    index: int
    object: Literal["embedding"] = "embedding"


class Usage(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    data: List[Embedding]
    model: str
    object: Literal["list"] = "list"
    usage: Usage


Response = EmbeddingResponse
