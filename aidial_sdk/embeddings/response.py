from typing import List, Literal

from aidial_sdk.utils.pydantic import ExtraForbidModel


class Embedding(ExtraForbidModel):
    embedding: List[float]
    index: int
    object: Literal["embedding"] = "embedding"


class Usage(ExtraForbidModel):
    prompt_tokens: int
    total_tokens: int


class CreateEmbeddingResponse(ExtraForbidModel):
    data: List[Embedding]
    model: str
    object: Literal["list"] = "list"
    usage: Usage


Response = CreateEmbeddingResponse
