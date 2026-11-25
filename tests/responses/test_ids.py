import re

import pytest

from aidial_sdk.responses import _ids

_PREFIXES = {
    "RESPONSE_PREFIX": "resp",
    "MESSAGE_PREFIX": "msg",
    "REASONING_PREFIX": "rs",
    "FUNCTION_CALL_PREFIX": "fc",
    "CUSTOM_TOOL_CALL_PREFIX": "ctc",
    "WEB_SEARCH_PREFIX": "ws",
    "IMAGE_GENERATION_PREFIX": "ig",
    "CALL_PREFIX": "call",
}


@pytest.mark.parametrize("name, prefix", _PREFIXES.items())
def test_prefix_constants(name: str, prefix: str):
    assert getattr(_ids, name) == prefix


@pytest.mark.parametrize("prefix", _PREFIXES.values())
def test_shape(prefix: str):
    assert re.fullmatch(rf"{prefix}_[0-9a-f]{{32}}", _ids.new_id(prefix))


def test_unique():
    ids = {_ids.new_id("msg") for _ in range(1000)}
    assert len(ids) == 1000
