import base64
from io import BytesIO
from typing import Tuple

import aiohttp
from PIL import Image


def get_image_base64_size(image_base64: str) -> Tuple[int, int]:
    image_binary = base64.b64decode(image_base64)
    img = Image.open(BytesIO(image_binary))
    return img.size


def bytes_to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode()


async def download_image_as_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.content.read()


async def download_image_as_base64(url: str) -> str:
    return bytes_to_base64(await download_image_as_bytes(url))
