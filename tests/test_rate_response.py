from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from tests.applications.single_choice_application import SingleChoiceApplication


def test_rate_response():
    dial_app = DIALApp()
    dial_app.add_chat_completion("test_app", SingleChoiceApplication())

    test_app = TestClient(dial_app)

    response = test_app.post(
        "/openai/deployments/test_app/rate",
        json={
            "responseId": "123",
            "rate": True,
        },
    )

    assert response.status_code == 200
