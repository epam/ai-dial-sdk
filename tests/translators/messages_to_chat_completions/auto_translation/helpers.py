from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from anthropic import AsyncAnthropic, AsyncStream
from anthropic.types import Message, RawMessageStreamEvent
from anthropic.types.message_create_params import MessageCreateParamsBase
from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai.types.chat import ChatCompletion as OpenAIChatCompletion
from openai.types.chat.completion_create_params import (
    CompletionCreateParamsBase,
)

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from aidial_sdk.deployment._headers import DIAL_DEPLOYMENT_ID

DUMMY_API_KEY = "test-api-key"

# The deployment is chosen by the x-dial-deployment-id header,
# the model field is never trusted
DUMMY_CHAT_REQUEST: CompletionCreateParamsBase = {
    "model": "ignored",
    "messages": [{"role": "user", "content": "Hello"}],
}

DUMMY_ANTHROPIC_REQUEST: MessageCreateParamsBase = {
    "model": "ignored",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello"}],
}

Chat = Callable[[Request, Response], Awaitable[None]]


class ScriptedChatCompletion(ChatCompletion):
    def __init__(self, chat: Chat) -> None:
        self.chat = chat
        self.requests: list[Request] = []

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        self.requests.append(request)
        await self.chat(request, response)


def replying(text: str) -> ScriptedChatCompletion:
    async def _reply(request: Request, response: Response) -> None:
        with response.create_single_choice() as choice:
            choice.append_content(text)

    return ScriptedChatCompletion(_reply)


class AnthropicClient(AsyncAnthropic):
    async def final_message(self, *, stream: bool, **params: Any) -> Message:
        request = {**DUMMY_ANTHROPIC_REQUEST, **params}
        if stream:
            async with self.messages.stream(**request) as message_stream:
                parsed = await message_stream.get_final_message()
            return Message.model_validate(parsed.model_dump(exclude_none=True))
        else:
            return await self.messages.create(**request)

    async def stream_events(
        self, **params: Any
    ) -> AsyncStream[RawMessageStreamEvent]:
        return await self.messages.create(
            **{**DUMMY_ANTHROPIC_REQUEST, **params}, stream=True
        )

    async def response_headers(self, *, stream: bool) -> httpx.Headers:
        async with self.messages.with_streaming_response.create(
            **DUMMY_ANTHROPIC_REQUEST, stream=stream
        ) as response:
            return response.headers

    async def stream_event_names(self) -> list[str]:
        async with self.messages.with_streaming_response.create(
            **DUMMY_ANTHROPIC_REQUEST, stream=True
        ) as response:
            return [
                line.removeprefix("event: ")
                async for line in response.iter_lines()
                if line.startswith("event: ")
            ]


class OpenAIClient(AsyncOpenAI):
    async def final_message(self, *, stream: bool) -> OpenAIChatCompletion:
        if stream:
            async with self.chat.completions.stream(
                **DUMMY_CHAT_REQUEST
            ) as completion_stream:
                return await completion_stream.get_final_completion()
        else:
            return await self.chat.completions.create(**DUMMY_CHAT_REQUEST)


class AzureOpenAIClient(AsyncAzureOpenAI, OpenAIClient):
    pass


class AppClient:
    def __init__(self, app: DIALApp, deployment: str | None = "foo") -> None:
        self._app = app
        self._deployment = deployment

    def with_deployment(self, deployment: str | None) -> "AppClient":
        return AppClient(self._app, deployment)

    def anthropic(self) -> AnthropicClient:
        return AnthropicClient(
            base_url="http://dial-app/anthropic",
            # Required by the SDK; DIAL apps read the `api-key` header
            api_key="-",
            **self._options(),
        )

    def openai(self) -> OpenAIClient:
        return OpenAIClient(
            base_url="http://dial-app/openai/v1",
            api_key="-",
            **self._options(),
        )

    def legacy_openai(self) -> AzureOpenAIClient:
        return AzureOpenAIClient(
            azure_endpoint="http://dial-app",
            azure_deployment=self._deployment,
            api_version="2024-10-21",
            api_key=DUMMY_API_KEY,
            **self._options(),
        )

    def _options(self) -> dict[str, Any]:
        headers = {"api-key": DUMMY_API_KEY}
        if self._deployment is not None:
            headers[DIAL_DEPLOYMENT_ID] = self._deployment

        return {
            "max_retries": 0,
            "default_headers": headers,
            "http_client": httpx.AsyncClient(
                # httpx<0.28 types the ASGI messages as dict
                transport=httpx.ASGITransport(
                    self._app,  # type: ignore
                    raise_app_exceptions=False,
                )
            ),
        }
