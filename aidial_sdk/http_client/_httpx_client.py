from types import NoneType
from typing import Type, Optional
from urllib.parse import urljoin

import httpx

from ._base import BaseHTTPClient, HttpRequestOptions, ResponseT


class HttpxClient(BaseHTTPClient):
    __base_url: Optional[str] = None

    def set_dial_base_url(self, base_url: Optional[str]) -> None:
        self.__base_url = base_url

    async def request(self, options: HttpRequestOptions, cast_to: Type[ResponseT]) -> ResponseT:
        if not self.__base_url:
            raise ValueError("Base URL is required to make a request. Pls set one in DIALApp")

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=options.method,
                url=urljoin(self.__base_url, options.path),
                params=options.params,
                headers=options.headers
            )
            response.raise_for_status()
            if cast_to is NoneType:
                return None
            return cast_to(**response.json())