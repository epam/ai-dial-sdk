from examples.image_size.app.main import app
from tests.utils.client import create_test_client


def test_app():
    client = create_test_client(app, name="image-size")

    attachment = {
        "type": "image/png",
        "data": "iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg==",
        "title": "Image",
    }

    response = client.post(
        "chat/completions",
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
