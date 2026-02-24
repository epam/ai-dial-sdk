from typing import Literal

from aidial_sdk.utils.pydantic import ExtraAllowModel


class Embedding(ExtraAllowModel):
    embedding: str | list[float]
    index: int
    object: Literal["embedding"] = "embedding"


class Usage(ExtraAllowModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(ExtraAllowModel):
    data: list[Embedding]
    model: str
    object: Literal["list"] = "list"
    usage: Usage


Response = EmbeddingResponse
