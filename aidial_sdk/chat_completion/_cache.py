from enum import Enum

from aidial_sdk.deployment._headers import DIAL_CACHE_POLICY


class CacheBreakpointPath:
    path: str

    def __init__(self, path: str) -> None:
        self.path = path

    @classmethod
    def messages(cls, idx: int):
        return cls(f"prefix.body.messages[{idx}]")

    @classmethod
    def tools(cls, idx: int):
        return cls(f"prefix.body.tools[{idx}]")


class CachePolicyHeader(Enum):
    AVAILABILITY_PRIORITY = "availability-priority"
    CACHE_PRIORITY = "cache-priority"

    def to_headers(self):
        return {DIAL_CACHE_POLICY: self.value}
