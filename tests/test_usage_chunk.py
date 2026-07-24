from aidial_sdk.chat_completion.chunks import UsageChunk


def test_usage_chunk_with_token_details():
    chunk = UsageChunk(
        prompt_tokens=10,
        completion_tokens=20,
        prompt_tokens_details={"cached_tokens": 3, "cache_write_tokens": 5},
        completion_tokens_details={"reasoning_tokens": 7},
    )
    assert chunk.to_dict() == {
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "prompt_tokens_details": {
                "cached_tokens": 3,
                "cache_write_tokens": 5,
            },
            "completion_tokens_details": {"reasoning_tokens": 7},
        }
    }


def test_usage_chunk_without_token_details():
    chunk = UsageChunk(
        prompt_tokens=10,
        completion_tokens=20,
        prompt_tokens_details=None,
        completion_tokens_details=None,
    )
    assert chunk.to_dict() == {
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }
    }
