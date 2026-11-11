from typing import Any, get_args

from openai.types.responses import (
    Response,
    ResponseError,
    ResponseOutputMessage,
)
from openai.types.responses.response import IncompleteDetails

from aidial_sdk.responses.enums import (
    ErrorCode,
    IncompleteReason,
    ItemStatus,
    MessagePhase,
    ResponseStatus,
)


def _literal_values(annotation: Any) -> set[str]:
    """Collects the values of a (possibly Optional) Literal annotation."""
    values: set[str] = set()
    for arg in get_args(annotation) or (annotation,):
        if get_args(arg):
            values |= _literal_values(arg)
        elif isinstance(arg, str):
            values.add(arg)
    return values


def _field_values(model: Any, field: str) -> set[str]:
    # `__annotations__` rather than `model_fields`: the latter is pydantic v2 only
    return _literal_values(model.__annotations__[field])


def test_error_code_matches_openai():
    expected = _field_values(ResponseError, "code")
    assert {e.value for e in ErrorCode} == expected


def test_item_status_matches_openai():
    expected = _field_values(ResponseOutputMessage, "status")
    assert {e.value for e in ItemStatus} == expected


def test_incomplete_reason_matches_openai():
    expected = _field_values(IncompleteDetails, "reason")
    assert {e.value for e in IncompleteReason} == expected


def test_message_phase_matches_openai():
    expected = _field_values(ResponseOutputMessage, "phase")
    assert {e.value for e in MessagePhase} == expected


def test_response_status_is_a_subset_of_openai():
    # `queued` needs `background`, which is rejected, and `cancelled` is
    # never produced, so only a subset is exposed. A status openai adds
    # later changes the difference and fails here, so it gets decided
    # rather than missed.
    openai_values = _field_values(Response, "status")
    values = {e.value for e in ResponseStatus}
    assert values <= openai_values
    assert openai_values - values == {"queued", "cancelled"}
