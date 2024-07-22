from enum import Enum

import aiohttp
import httpx
import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing_extensions import assert_never

app = FastAPI()


class Library(str, Enum):
    requests = "requests"
    httpx_sync = "httpx_sync"
    httpx_async = "httpx_async"
    aiohttp = "aiohttp"


class Request(BaseModel):
    url: str
    lib: Library
    headers: dict


@app.post("/")
async def handle(request: Request):
    url = request.url
    lib = request.lib
    headers = request.headers

    if lib == Library.requests:
        response = requests.get(url, headers=headers)
        status_code = response.status_code
        content = response.json()

    elif lib == Library.httpx_async:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            status_code = response.status_code
            content = response.json()

    elif lib == Library.httpx_sync:
        with httpx.Client() as client:
            response = client.get(url, headers=headers)
            status_code = response.status_code
            content = response.json()

    elif lib == Library.aiohttp:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                status_code = response.status
                content = await response.json()

    else:
        assert_never(lib)

    return JSONResponse(
        status_code=status_code,
        content=content,
    )
