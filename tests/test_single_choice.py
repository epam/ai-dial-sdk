from tests.applications.single_choice import SingleChoiceApplication
from tests.utils.chunks import check_sse_stream, create_single_choice_chunk
from tests.utils.client import create_app_client


def test_single_choice():
    client = create_app_client(SingleChoiceApplication())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "Test content"}],
            "stream": False,
        },
    )

    assert response.status_code == 200 and response.json() == {
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "Test response content",
                },
            }
        ],
        "usage": None,
        "id": "test_id",
        "created": 0,
        "object": "chat.completion",
    }


def test_single_choice_streaming():
    client = create_app_client(SingleChoiceApplication())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "Test content"}],
            "stream": True,
        },
    )

    check_sse_stream(
        response.iter_lines(),
        [
            create_single_choice_chunk({"role": "assistant"}),
            create_single_choice_chunk({"content": "Test response content"}),
            create_single_choice_chunk({}, "stop"),
        ],
    )
