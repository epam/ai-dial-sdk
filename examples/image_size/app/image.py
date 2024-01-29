import base64
from io import BytesIO
from typing import Tuple

import requests
from PIL import Image


def get_image_base64_size(image_base64) -> Tuple[int, int]:
    image_binary = base64.b64decode(image_base64)
    img = Image.open(BytesIO(image_binary))
    return img.size


def bytes_to_base64(bytes: bytes) -> str:
    return base64.b64encode(bytes).decode()


def download_image_as_bytes(url: str) -> bytes:
    response = requests.get(url)
    response.raise_for_status()
    return response.content


def download_image_as_base64(url: str) -> str:
    return bytes_to_base64(download_image_as_bytes(url))
