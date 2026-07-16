import json
import logging
import sys

from aidial_sdk.utils.json_log_formatter import JsonLogFormatter


def _format(template: dict, **record_fields) -> dict:
    record = logging.makeLogRecord(record_fields)
    return json.loads(JsonLogFormatter(template).format(record))


def test_escapes_quotes_newlines_and_percent():
    msg = 'has "quotes", a\nnewline, a \\ backslash and 50% off'
    out = _format({"message": "%(message)s"}, msg=msg)
    assert out["message"] == msg  # round-trips => json.dumps escaped it


def test_message_args_are_interpolated():
    out = _format({"message": "%(message)s"}, msg="hi %s", args=("bob",))
    assert out["message"] == "hi bob"


def test_missing_field_renders_empty():
    out = _format({"trace": "%(otelTraceID)s"})
    assert out["trace"] == ""


def test_nested_template():
    out = _format({"a": {"b": "%(levelname)s"}}, levelname="INFO")
    assert out["a"]["b"] == "INFO"


def test_non_string_leaves_pass_through():
    out = _format({"schema": 1, "on": True, "n": None})
    assert out == {"schema": 1, "on": True, "n": None}


def test_otel_fields_auto_added_when_present():
    out = _format(
        {"msg": "%(message)s"},
        msg="hi",
        otelTraceID="abc",
        otelSpanID="def",
        otelTraceSampled=True,
    )
    assert out == {
        "msg": "hi",
        "otelTraceID": "abc",
        "otelSpanID": "def",
        "otelTraceSampled": True,
    }


def test_otel_fields_not_added_when_absent():
    out = _format({"msg": "%(message)s"}, msg="hi")
    assert out == {"msg": "hi"}


def test_otel_field_referenced_in_template_is_not_duplicated():
    out = _format(
        {"trace_id": "%(otelTraceID)s", "span_id": "%(otelSpanID)s"},
        otelTraceID="abc",
        otelSpanID="def",
    )
    # Renamed via the template -> no extra otelTraceID/otelSpanID keys.
    assert out == {"trace_id": "abc", "span_id": "def"}


def test_exception_via_exc_text():
    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()
    out = _format({"err": "%(exc_text)s"}, msg="x", exc_info=exc_info)
    assert "ValueError: boom" in out["err"]
