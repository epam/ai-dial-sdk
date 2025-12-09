import pytest
from starlette.testclient import TestClient

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


class TokenEchoApp(ChatCompletion):
    async def chat_completion(self, request: Request, response: Response):
        with response.create_choice() as choice:
            choice.append_content("ok")


def create_client(app_instance: ChatCompletion):
    app = DIALApp().add_chat_completion("echo", app_instance)
    return TestClient(
        app,
        base_url="https://testserver/openai/deployments/echo",
        headers={"Api-Key": "test-api-key"},
    )


class AssertingApp(TokenEchoApp):
    def __init__(self, expected_jwt, expected_bearer_token):
        super().__init__()
        self.expected_jwt = expected_jwt
        self.expected_bearer_token = expected_bearer_token

    async def chat_completion(self, request: Request, response: Response):
        assert request.jwt == self.expected_jwt
        assert request.bearer_token == self.expected_bearer_token
        await super().chat_completion(request, response)


@pytest.mark.parametrize(
    "authz_header, expected_jwt, expected_bearer",
    [
        (None, None, None),
        ("Bearer abc123", "Bearer abc123", "abc123"),
        ("Bearer   spaced", "Bearer   spaced", "spaced"),
        ("bearer lower", "bearer lower", "lower"),
        ("Token abc", "Token abc", None),
        ("Bearer", "Bearer", None),
    ],
)
def test_bearer_token_parsing(authz_header, expected_jwt, expected_bearer):
    client = create_client(AssertingApp(expected_jwt, expected_bearer))

    headers = {}
    if authz_header is not None:
        headers["Authorization"] = authz_header

    response = client.post(
        "chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=headers,
    )

    assert response.status_code == 200


def test_bearer_token_is_removed_from_headers_forwarding():
    class InspectHeadersApp(TokenEchoApp):
        async def chat_completion(self, request: Request, resp: Response):
            assert "Authorization" not in request.headers
            assert "Api-Key" not in request.headers
            await super().chat_completion(request, resp)

    client = create_client(InspectHeadersApp())

    response = client.post(
        "chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer tok", "Api-Key": "ignored"},
    )

    assert response.status_code == 200
