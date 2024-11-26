from fastapi.testclient import TestClient

from examples.echo.app import app


def test_app():
    client = TestClient(
        app,
        headers={"Api-Key": "dial_api_key"},
        base_url="http://testserver/openai/deployments/echo",
    )

    content = "Hello world!"
    attachment = {
        "type": "image/png",
        "url": "image-url",
        "title": "Image",
    }

    response = client.post(
        "chat/completions",
        params={"api-version": "2023-03-15-preview"},
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
