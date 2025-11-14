import dataclasses
from typing import List

import pytest

from aidial_sdk._pydantic import BaseModel, ValidationError
from aidial_sdk.chat_completion import (
    Attachment,
    FunctionCall,
    Status,
    ToolCall,
)
from aidial_sdk.chat_completion.request import Stage
from tests.utils.pydantic import model_dump, model_parse


@dataclasses.dataclass
class TestCase:
    __test__ = False
    obj: BaseModel
    dct: dict

    def get_id(self) -> str:
        return type(self.obj).__name__


_test_cases: List[TestCase] = [
    TestCase(
        ToolCall(
            id="tool-call-id",
            type="function",
            function=FunctionCall(name="func-name", arguments="{}"),
        ),
        {
            "id": "tool-call-id",
            "type": "function",
            "function": {"name": "func-name", "arguments": "{}"},
        },
    ),
    TestCase(
        Attachment(type="text/plain", data="test"),
        {"type": "text/plain", "data": "test"},
    ),
    TestCase(
        Stage(name="Testing", status=Status.COMPLETED, content="test"),
        {"name": "Testing", "status": "completed", "content": "test"},
    ),
]


@pytest.fixture(params=_test_cases, ids=lambda x: x.get_id())
def test_case(request) -> TestCase:
    return request.param


def _check_ser_deser(obj: BaseModel):
    dct = model_dump(obj)
    obj2 = model_parse(type(obj), dct, allow_extra_fields=False)
    assert obj == obj2


def test_index_field_ser_deser(test_case: TestCase):
    _check_ser_deser(test_case.obj)


def test_index_field_ignore_int(test_case: TestCase):
    tool_call = model_parse(
        type(test_case.obj),
        {**test_case.dct, **{"index": 101}},
        allow_extra_fields=False,
    )
    _check_ser_deser(tool_call)


def test_index_field_fail_on_str(test_case: TestCase):
    if isinstance(test_case.obj, ToolCall):
        err = r"index[\s\S]*value is not a valid integer"
    else:
        err = r"(Extra inputs are not permitted|extra fields not permitted)"

    with pytest.raises(ValidationError, match=err):
        model_parse(
            type(test_case.obj),
            {**test_case.dct, **{"index": "value"}},
            allow_extra_fields=False,
        )


def test_index_field_fail_on_extra_fields(test_case: TestCase):
    with pytest.raises(
        ValidationError,
        match=r"(Extra inputs are not permitted|extra fields not permitted)",
    ):
        model_parse(
            type(test_case.obj),
            {**test_case.dct, **{"index2": "whatever"}},
            allow_extra_fields=False,
        )
