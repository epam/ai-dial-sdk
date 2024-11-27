import base64
from io import BytesIO
from typing import Tuple

from PIL import Image

from examples.render_text.app.main import app
from tests.utils.client import create_test_client


def test_app():
    client = create_test_client(app, name="render-text")

    response = client.post(
        "chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "base64,Hello world!",
                }
            ]
        },
    )

    body = response.json()

    response_message = body["choices"][0]["message"]
    response_content = response_message["content"]
    assert response_content.startswith("![Image](data:image/png;base64,")

    attachment = response_message["custom_content"]["attachments"][0]
    assert attachment["type"] == "image/png"
    assert attachment["title"] == "Image"
    data = attachment["data"]
    assert data is not None and get_image_base64_size(data) == (200, 100)


def get_image_base64_size(image_base64) -> Tuple[int, int]:
    image_binary = base64.b64decode(image_base64)
    img = Image.open(BytesIO(image_binary))
    return img.size
