import base64
from io import BytesIO
from typing import Tuple

from fastapi.testclient import TestClient
from PIL import Image

from examples.render_text.app.main import app

http_client = TestClient(app)


def test_app():
    response = http_client.post(
        "/openai/deployments/render-text/chat/completions?api-version=2023-03-15-preview",
        headers={"Api-Key": "dial_api_key"},
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Hello world!",
                }
            ]
        },
    )

    body = response.json()

    response_message = body["choices"][0]["message"]
    response_content = response_message["content"]
    assert response_content == "Image was generated successfully"

    attachment = response_message["custom_content"]["attachments"][0]
    assert attachment["type"] == "image/png"
    assert attachment["title"] == "Image"
    data = attachment["data"]
    assert data is not None and get_image_base64_size(data) == (200, 100)


def get_image_base64_size(image_base64) -> Tuple[int, int]:
    image_binary = base64.b64decode(image_base64)
    img = Image.open(BytesIO(image_binary))
    return img.size
