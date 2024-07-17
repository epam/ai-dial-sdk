from typing import List, Literal, Union

from aidial_sdk.utils.pydantic import ExtraForbidModel


class Embedding(ExtraForbidModel):
    embedding: Union[str, List[float]]
    index: int
    object: Literal["embedding"] = "embedding"


class Usage(ExtraForbidModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(ExtraForbidModel):
    data: List[Embedding]
    model: str
    object: Literal["list"] = "list"
    usage: Usage


Response = EmbeddingResponse
