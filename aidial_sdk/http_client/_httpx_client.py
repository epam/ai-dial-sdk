from types import NoneType
from typing import Type

import httpx

from ._base import BaseHTTPClient, HttpRequestOptions, ResponseT


class HttpxClient(BaseHTTPClient):
    async def request(self, options: HttpRequestOptions, cast_to: Type[ResponseT]) -> ResponseT:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=options.method,
                url=httpx.URL(options.url),
                params=options.params,
                headers=options.headers
            )
            response.raise_for_status()
            if cast_to is NoneType:
                return None
            return cast_to.model_validate(response.json())
