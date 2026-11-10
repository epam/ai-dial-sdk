import re

import pytest

from aidial_sdk.responses._context import _ResponseContext
from aidial_sdk.responses.enums import ItemStatus
from aidial_sdk.responses.models import ResponseObject
from aidial_sdk.responses.tool_call import CustomToolCall, FunctionCall
from tests.responses.conftest import (
    _FixedIdContext,
    drain,
)


@pytest.mark.parametrize("builder", [FunctionCall, CustomToolCall])
def test_call_id_is_generated(builder):
    response_object = ResponseObject(id="resp_1", created_at=0, model="m")
    call = builder(_ResponseContext(response_object, stream=True), "f")

    assert re.fullmatch(r"call_[0-9a-f]{32}", call.call_id)


@pytest.mark.parametrize("builder", [FunctionCall, CustomToolCall])
def test_call_id_is_kept(builder):
    call = builder(_FixedIdContext(stream=True), "f", call_id="call_x")

    assert call.call_id == "call_x"


@pytest.mark.parametrize(
    "builder, field", [(FunctionCall, "arguments"), (CustomToolCall, "input")]
)
def test_nothing_appended(builder, field: str):
    ctx = _FixedIdContext(stream=True)
    builder(ctx, "f").close()

    *_, value_done, item_done = drain(ctx)

    assert value_done[field] == ""
    assert item_done["item"][field] == ""


def test_set_arguments_takes_a_string_as_is():
    call = FunctionCall(_FixedIdContext(stream=True), "f")

    call.set_arguments('{"a":1}')

    assert call._item.arguments == '{"a":1}'


def test_function_call_set_incomplete():
    call = FunctionCall(_FixedIdContext(stream=True), "f").set_incomplete()
    assert call._item.status == ItemStatus.IN_PROGRESS

    call.close()
    assert call._item.status == ItemStatus.INCOMPLETE


def test_custom_tool_call_has_no_status():
    ctx = _FixedIdContext(stream=True)
    CustomToolCall(ctx, "f").close()

    added, *_, done = drain(ctx)

    assert "status" not in added["item"]
    assert "status" not in done["item"]
