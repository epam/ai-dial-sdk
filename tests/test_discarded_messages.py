import json
from unittest.mock import Mock

import fastapi
import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp, HTTPException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from aidial_sdk.pydantic_v1 import SecretStr

DISCARDED_MESSAGES = list(range(0, 12))

dummy_request = fastapi.Request({"type": "http"})


def test_discarded_messages_returned():
    dial_app = DIALApp()
    chat_completion = Mock(spec=ChatCompletion)

    async def chat_completion_side_effect(_, res: Response) -> None:
        with res.create_single_choice():
            pass
        res.set_discarded_messages(DISCARDED_MESSAGES)

    chat_completion.chat_completion.side_effect = chat_completion_side_effect
    dial_app.add_chat_completion("test_app", chat_completion)

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Test content"}],
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    assert (
        response.json()["statistics"]["discarded_messages"]
        == DISCARDED_MESSAGES
    )


def test_discarded_messages_returned_as_last_chunk_in_stream():
    dial_app = DIALApp()
    chat_completion = Mock(spec=ChatCompletion)

    async def chat_completion_side_effect(_, res: Response) -> None:
        res.set_response_id("test_id")
        res.set_created(123)

        with res.create_single_choice():
            pass

        res.set_discarded_messages(DISCARDED_MESSAGES)

    chat_completion.chat_completion.side_effect = chat_completion_side_effect
    dial_app.add_chat_completion("test_app", chat_completion)

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Test content"}],
            "stream": True,
        },
        headers={"Api-Key": "TEST_API_KEY"},
    )

    def parse_chunk(data: str):
        return json.loads(data[len("data: ") :])

    def identity(data: str):
        return data

    parsers = [
        parse_chunk,
        identity,
        parse_chunk,
        identity,
        identity,
        identity,
    ]
    lines = [*response.iter_lines()]

    assert len(lines) == len(parsers)
    assert [parser(lines[i]) for i, parser in enumerate(parsers)] == [
        {
            "choices": [
                {
                    "index": 0,
                    "finish_reason": None,
                    "delta": {"role": "assistant"},
                }
            ],
            "usage": None,
            "id": "test_id",
            "created": 123,
            "object": "chat.completion.chunk",
        },
        "",
        {
            "choices": [{"index": 0, "finish_reason": "stop", "delta": {}}],
            "usage": None,
            "statistics": {"discarded_messages": DISCARDED_MESSAGES},
            "id": "test_id",
            "created": 123,
            "object": "chat.completion.chunk",
        },
        "",
        "data: [DONE]",
        "",
    ]


def test_discarded_messages_is_set_twice():
    request = Request(
        headers={},
        original_request=dummy_request,
        api_key_secret=SecretStr("dummy_key"),
        deployment_id="",
        messages=[],
    )

    response = Response(request)

    with response.create_single_choice():
        pass

    response.set_discarded_messages(DISCARDED_MESSAGES)

    with pytest.raises(HTTPException):
        response.set_discarded_messages(DISCARDED_MESSAGES)


def test_discarded_messages_is_set_before_choice():
    request = Request(
        headers={},
        original_request=dummy_request,
        api_key_secret=SecretStr("dummy_key"),
        deployment_id="",
        messages=[],
    )
    response = Response(request)

    with pytest.raises(HTTPException):
        response.set_discarded_messages(DISCARDED_MESSAGES)
