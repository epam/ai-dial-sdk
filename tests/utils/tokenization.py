from typing import Callable, Optional, Set, Union

from aidial_sdk.chat_completion.request import (
    ChatCompletionRequest,
    Message,
    Role,
)
from aidial_sdk.deployment.tokenize import (
    TokenizeRequest,
    TokenizeResponse,
    TokenizeResult,
    TokenizeSuccess,
)
from aidial_sdk.deployment.truncate_prompt import (
    TruncatePromptError,
    TruncatePromptRequest,
    TruncatePromptResponse,
    TruncatePromptResult,
    TruncatePromptSuccess,
)


def word_count_string(string: str) -> int:
    return len(string.split())


def word_count_message(message: Message) -> int:
    return word_count_string(message.content or "")


def word_count_request(request: ChatCompletionRequest) -> int:
    return sum(map(word_count_message, request.messages))


def word_count_tokenize(
    request: Union[ChatCompletionRequest, str]
) -> TokenizeResult:
    if isinstance(request, str):
        token_count = word_count_string(request)
    else:
        token_count = word_count_request(request)
    return TokenizeSuccess(token_count=token_count)


def make_batched_tokenize(
    tokenize: Callable[[Union[ChatCompletionRequest, str]], TokenizeResult]
) -> Callable[[TokenizeRequest], TokenizeResponse]:
    def ret(request: TokenizeRequest) -> TokenizeResponse:
        return TokenizeResponse(
            responses=[tokenize(req) for req in request.requests]
        )

    return ret


def default_truncate_prompt(
    request: ChatCompletionRequest,
    count_request_tokens: Callable[[ChatCompletionRequest], int],
    model_max_prompt_tokens: int,
) -> TruncatePromptResult:
    def _count_tokens_selected(indices: Set[int]) -> int:
        messages = [
            message
            for idx, message in enumerate(request.messages)
            if idx in indices
        ]
        sub_request = request.copy(update={"messages": messages})
        return count_request_tokens(sub_request)

    all_indices = set(range(0, len(request.messages)))

    max_prompt_tokens: Optional[int] = request.max_prompt_tokens
    if max_prompt_tokens is None:
        token_count = _count_tokens_selected(all_indices)
        if token_count > model_max_prompt_tokens:
            return TruncatePromptError(
                error=f"Token count of all messages ({token_count}) exceeds"
                f" the model maximum prompt tokens ({model_max_prompt_tokens}).",
            )
        return TruncatePromptSuccess(discarded_messages=[])

    token_count: int = 0
    found_user_message = False
    selected_indices: Set[int] = set()

    for idx in reversed(range(0, len(request.messages))):
        message = request.messages[idx]

        is_user_message = message.role == Role.USER
        is_last_user_message = not found_user_message and is_user_message
        found_user_message = found_user_message or is_user_message

        is_message_required = (
            message.role == Role.SYSTEM or is_last_user_message
        )

        if not is_message_required:
            continue

        selected_indices.add(idx)
        token_count = _count_tokens_selected(selected_indices)

    if token_count > max_prompt_tokens:
        return TruncatePromptError(
            error="Token count of the last user message and all system messages "
            f"({token_count}) exceeds the maximum prompt tokens ({max_prompt_tokens}).",
        )

    for idx in reversed(range(0, len(request.messages))):
        if idx in selected_indices:
            continue

        new_token_count = _count_tokens_selected({*selected_indices, idx})
        if new_token_count > max_prompt_tokens:
            break

        selected_indices.add(idx)
        token_count = new_token_count

    discarded_indices = all_indices - selected_indices
    return TruncatePromptSuccess(
        discarded_messages=list(sorted(discarded_indices))
    )


def make_batched_truncate_prompt(
    truncate_prompt: Callable[[ChatCompletionRequest], TruncatePromptResult],
) -> Callable[[TruncatePromptRequest], TruncatePromptResponse]:
    def ret(request: TruncatePromptRequest) -> TruncatePromptResponse:
        return TruncatePromptResponse(
            responses=[truncate_prompt(req) for req in request.requests]
        )

    return ret
