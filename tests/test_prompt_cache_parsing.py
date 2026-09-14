from aidial_sdk.chat_completion.request import (
    MessageContentTextPart,
    Request,
)
from tests.utils.chat_completion_validation import validate_chat_completion
from tests.utils.pydantic import model_dump

REQUEST = {
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Hello",
                    "prompt_cache_breakpoint": {"mode": "explicit"},
                }
            ],
        }
    ],
    "prompt_cache_key": "key-1",
    "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
}


def test_prompt_cache_parsing():
    def _request_validator(r: Request):
        assert model_dump(r, exclude_none=True) == REQUEST

        assert r.prompt_cache_key == "key-1"
        assert r.prompt_cache_options
        assert r.prompt_cache_options.mode == "explicit"
        assert r.prompt_cache_options.ttl == "30m"

        content = r.messages[0].content
        assert isinstance(content, list)
        part = content[0]
        assert isinstance(part, MessageContentTextPart)
        assert part.prompt_cache_breakpoint
        assert part.prompt_cache_breakpoint.mode == "explicit"

    validate_chat_completion(
        request=REQUEST,
        request_validator=_request_validator,
    )
