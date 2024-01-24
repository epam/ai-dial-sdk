from fastapi.testclient import TestClient

from examples.image_size.app.main import app

http_client = TestClient(app)


def test_app():
    attachment = {
        "type": "image/png",
        "data": "iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg==",
        "title": "Image",
    }

    response = http_client.post(
        "/openai/deployments/image-size/chat/completions?api-version=2023-03-15-preview",
        headers={"Api-Key": "dial_api_key"},
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "",
                    "custom_content": {"attachments": [attachment]},
                }
            ]
        },
    )

    body = response.json()
    response_message = body["choices"][0]["message"]
    response_content = response_message["content"]

    assert response_content == "Size: 5x5px"
