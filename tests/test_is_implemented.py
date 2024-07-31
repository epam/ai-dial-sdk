from aidial_sdk.chat_completion import (
    ChatCompletion,
    Request,
    Response,
    TokenizeRequest,
    TokenizeResponse,
    TruncatePromptRequest,
    TruncatePromptResponse,
)
from aidial_sdk.utils._reflection import has_method_implemented


class WithTokenize(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        pass

    async def tokenize(self, request: TokenizeRequest) -> TokenizeResponse:
        return TokenizeResponse(outputs=[])


class WithTruncatePrompt(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        pass

    async def truncate_prompt(
        self, request: TruncatePromptRequest
    ) -> TruncatePromptResponse:
        return TruncatePromptResponse(outputs=[])


def test_has_tokenize_implemented():
    assert has_method_implemented(WithTokenize(), "tokenize")
    assert not has_method_implemented(WithTruncatePrompt(), "tokenize")


def test_has_truncate_prompt_implemented():
    assert not has_method_implemented(WithTokenize(), "truncate_prompt")
    assert has_method_implemented(WithTruncatePrompt(), "truncate_prompt")
