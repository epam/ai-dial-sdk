from tests.utils.chat_completion_validation import validate_chat_completion


def test_max_prompt_tokens_is_set():
    validate_chat_completion(
        request={
            "messages": [{"role": "user", "content": "Test content"}],
            "max_prompt_tokens": 15,
        },
        request_validator=lambda r: r.max_prompt_tokens == 15,
    )


def test_max_prompt_tokens_is_unset():
    validate_chat_completion(
        request={
            "messages": [{"role": "user", "content": "Test content"}],
        },
        request_validator=lambda r: not r.max_prompt_tokens,
    )
