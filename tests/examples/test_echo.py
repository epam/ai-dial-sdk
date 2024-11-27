from examples.echo.app import app
from tests.utils.client import create_test_client


def test_app():
    client = create_test_client(app, name="echo")

    content = "Hello world!"
    attachment = {
        "type": "image/png",
        "url": "image-url",
        "title": "Image",
    }

    response = client.post(
        "chat/completions",
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
