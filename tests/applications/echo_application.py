from typing_extensions import override

from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from aidial_sdk.deployment.tokenize import TokenizeRequest, TokenizeResponse
from aidial_sdk.deployment.truncate_prompt import (
    TruncatePromptRequest,
    TruncatePromptResponse,
)
from tests.utils.tokenization import (
    default_truncate_prompt,
    make_batched_tokenize,
    make_batched_truncate_prompt,
    word_count_request,
    word_count_tokenize,
)


class EchoApplication(ChatCompletion):
    model_max_prompt_tokens: int

    def __init__(self, model_max_prompt_tokens: int):
        self.model_max_prompt_tokens = model_max_prompt_tokens

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        response.set_response_id("test_id")
        response.set_created(0)

        content = request.messages[-1].content or ""

        with response.create_single_choice() as choice:
            choice.append_content(content)

    @override
    async def tokenize(self, request: TokenizeRequest) -> TokenizeResponse:
        return make_batched_tokenize(word_count_tokenize)(request)

    @override
    async def truncate_prompt(
        self, request: TruncatePromptRequest
    ) -> TruncatePromptResponse:
        return make_batched_truncate_prompt(
            lambda req: default_truncate_prompt(
                req, word_count_request, self.model_max_prompt_tokens
            )
        )(request)
