from fastapi.testclient import TestClient

from examples.echo.app import app

http_client = TestClient(app)


def test_app():
    content = "Hello world!"
    attachment = {
        "type": "image/png",
        "url": "image-url",
        "title": "Image",
    }

    response = http_client.post(
        "/openai/deployments/echo/chat/completions?api-version=2023-03-15-preview",
        headers={"Api-Key": "dial_api_key"},
        json={
            "messages": [
                {
                    "role": "user",
                    "content": content,
                    "custom_content": {"attachments": [attachment]},
                }
            ]
        },
    )

    body = response.json()
    response_message = body["choices"][0]["message"]

    response_content = response_message["content"]
    assert response_content == content

    response_attachment = response_message["custom_content"]["attachments"][0]
    assert response_attachment == attachment
