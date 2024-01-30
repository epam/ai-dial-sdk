import base64
import os
import textwrap
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont


def text_to_image_base64(text: str, img_size=(200, 100), font_size=20) -> str:
    img = Image.new("RGB", img_size, color="yellow")
    d = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("Monaco.ttf", font_size)
    except IOError:
        font = ImageFont.load_default(font_size)  # type: ignore

    wrapped_text = textwrap.fill(text, width=15)

    d.text((10, 10), wrapped_text, fill=(0, 0, 0), font=font)

    img_buffer = BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    img_base64 = base64.b64encode(img_buffer.getvalue()).decode()

    return img_base64


def upload_png_image(dial_url: str, filepath: str, image_base64: str) -> str:
    appdata = requests.get(f"{dial_url}/v1/bucket").json()["appdata"]

    image_bytes = base64.b64decode(image_base64)
    image_file = BytesIO(image_bytes)
    files = {"file": (os.path.basename(filepath), image_file, "image/png")}

    metadata = requests.put(
        f"{dial_url}/v1/files/{appdata}/{filepath}", files=files
    ).json()

    return metadata["url"]
