import base64
from io import BytesIO

from PIL import Image


def get_image_base64_dimensions(image_base64) -> tuple[int, int]:
    image_binary = base64.b64decode(image_base64)
    img = Image.open(BytesIO(image_binary))
    return img.size
