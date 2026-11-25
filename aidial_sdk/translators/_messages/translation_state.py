import hashlib
import re
from functools import lru_cache

# OpenAI allows `^[a-zA-Z0-9_-]{1,64}$`, but Gemini on Vertex AI also requires a
# leading letter or underscore, and the DIAL Vertex adapter doesn't alias such
# names yet: https://github.com/epam/ai-dial-adapter-vertexai/issues/576
# Once it does, use OpenAI's rule here and drop the `t_` prefix below.
_CONFORMING_TOOL_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$")
_DISALLOWED_CHAR = re.compile(r"[^a-zA-Z0-9_-]")
_ALLOWED_LEAD = re.compile(r"^[a-zA-Z_]")

_MAX_LENGTH = 64
_DIGEST_LENGTH = 8
_HEAD_LENGTH = _MAX_LENGTH - _DIGEST_LENGTH - 1


@lru_cache(4096)
def _to_alias(name: str) -> str:
    digest = hashlib.sha256(name.encode()).hexdigest()[:_DIGEST_LENGTH]
    head = _DISALLOWED_CHAR.sub("_", name)
    if not _ALLOWED_LEAD.match(head):
        head = f"t_{head}"
    return f"{head[:_HEAD_LENGTH]}_{digest}"


class TranslationState:
    def __init__(self) -> None:
        self._originals: dict[str, str] = {}

    def to_upstream_tool_name(self, name: str) -> str:
        if not name or _CONFORMING_TOOL_NAME.match(name):
            return name
        alias = _to_alias(name)
        self._originals[alias] = name
        return alias

    def to_client_tool_name(self, name: str) -> str:
        return self._originals.get(name, name)
