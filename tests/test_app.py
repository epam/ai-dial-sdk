from unittest.mock import Mock

from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Response


def test_discarded_messages_returned():
    dial_app = DIALApp()
    chat_completion = Mock(spec=ChatCompletion)

    async def chat_completion_side_effect(_, res: Response) -> None:
        with res.create_single_choice():
            pass
        res.set_discarded_messages(12)

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

    assert response.json()["statistics"]["discarded_messages"] == 12
