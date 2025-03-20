from typing import List, Literal, Union

from aidial_sdk.utils.pydantic import ExtraAllowModel


class Embedding(ExtraAllowModel):
    embedding: Union[str, List[float]]
    index: int
    object: Literal["embedding"] = "embedding"


class Usage(ExtraAllowModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(ExtraAllowModel):
    data: List[Embedding]
    model: str
    object: Literal["list"] = "list"
    usage: Usage


Response = EmbeddingResponse
