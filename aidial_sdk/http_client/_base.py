from abc import ABC, abstractmethod
from typing import Literal, Optional, Mapping, Any, final, TypeVar, Type, Union

from aidial_sdk.pydantic_v1 import BaseModel


@final
class HttpRequestOptions(BaseModel):
    method: Literal["GET", "PUT", "POST", "DELETE"]
    path: str
    params: Optional[Mapping[str, Any]] = None
    headers: Optional[Mapping[str, Any]] = None


ResponseT = TypeVar(
    "ResponseT",
    bound=Union[BaseModel, None]
)


class BaseHTTPClient(ABC):
    __base_url: str = None

    @abstractmethod
    async def request(
            self,
            options: HttpRequestOptions,
            cast_to: Type[ResponseT],
    ) -> ResponseT:
        ...

    @abstractmethod
    def set_base_url(self, url: str) -> None:
        ...
