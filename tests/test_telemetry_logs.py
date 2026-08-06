import json
import os
import re
import subprocess
import sys

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run(
    logs: str,
    *,
    env: dict[str, str] | None = None,
    telemetry: str | None = None,
    root_logger: bool = False,
    preamble: str = "",
) -> list[str]:
    script = [
        "import logging",
        preamble,
        "import aidial_sdk",  # runs configure_sdk_logger(), reading the env
    ]
    if telemetry:
        script += [
            "from aidial_sdk.telemetry.init import init_telemetry",
            "from aidial_sdk.telemetry.types import LogsConfig, TracingConfig, TelemetryConfig",
            f"init_telemetry(None, {telemetry})",
        ]
    if root_logger:
        script.append("aidial_sdk.configure_root_logger()")
    script.append(logs)

    err = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "\n".join(script)],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    ).stderr
    return [_ANSI.sub("", ln) for ln in err.splitlines() if ln.strip()]


def emit(msg, *, logger="app", level="warning", set_level=True):
    stmt = f"_l = logging.getLogger({logger!r})\n"
    if set_level:
        stmt += f"_l.setLevel(logging.{level.upper()})\n"
    return stmt + f"_l.{level}({msg!r})"


def parse_json(lines: list[str]) -> dict:
    assert len(lines) == 1, f"expected 1 line, got {lines}"
    return json.loads(lines[0])


# ---------------------------------------------------------------------------
# §1 — DIAL SDK formatter (no telemetry)
# ---------------------------------------------------------------------------


def test_text_is_the_default_format():
    lines = run(emit("hello", logger="aidial_sdk"))
    assert len(lines) == 1
    assert "WARNING" in lines[0]
    assert "| aidial_sdk |" in lines[0]
    assert lines[0].endswith("| hello")


def test_json_format_renders_one_json_object_per_record():
    obj = parse_json(
        run(
            emit("hello", logger="aidial_sdk"),
            env={"DIAL_SDK_LOG_FORMAT": "json"},
        )
    )
    assert isinstance(obj.pop("process"), str)
    assert isinstance(obj.pop("time"), str)
    assert obj == {
        "level": "WARNING",
        "logger": "aidial_sdk",
        "message": "hello",
    }


def test_custom_text_format_is_honored():
    lines = run(
        emit("hello", logger="aidial_sdk"),
        env={"DIAL_SDK_TEXT_LOG_FORMAT": "%(levelname)s>>%(message)s"},
    )
    assert lines == ["WARNING>>hello"]


def test_custom_json_format_is_honored():
    obj = parse_json(
        run(
            emit("hello", logger="aidial_sdk"),
            env={
                "DIAL_SDK_LOG_FORMAT": "json",
                "DIAL_SDK_JSON_LOG_FORMAT": '{"lvl":"%(levelname)s","msg":"%(message)s"}',
            },
        )
    )
    assert obj == {"lvl": "WARNING", "msg": "hello"}


def test_level_defaults_to_warning_hiding_info():
    assert (
        run(emit("hello", logger="aidial_sdk", level="info", set_level=False))
        == []
    )


def test_dial_sdk_log_sets_the_level():
    lines = run(
        emit("hello", logger="aidial_sdk", level="info", set_level=False),
        env={"DIAL_SDK_LOG": "INFO"},
    )
    assert len(lines) == 1 and lines[0].endswith("| hello")


def test_text_format_with_trace_placeholder_drops_line_when_tracing_off():
    # §1: text has no missing-field fallback — a %(otelTraceID)s placeholder with
    # tracing off raises KeyError and the record is dropped.
    lines = run(
        emit("hello", logger="aidial_sdk"),
        env={"DIAL_SDK_TEXT_LOG_FORMAT": "trace=%(otelTraceID)s %(message)s"},
    )
    assert any("Logging error" in ln for ln in lines)
    assert not any(ln == "hello" for ln in lines)


# §1 with tracing on: the JSON formatter auto-adds every otel* field on the
# record. Tracing is enabled without correlation (logging=False) so the SDK's own
# JSON formatter stays in charge.
_TRACING_NO_CORRELATION = "TelemetryConfig(tracing=TracingConfig(logging=False), logs=None, metrics=None)"


def test_json_auto_adds_otel_fields_when_tracing_on():
    obj = parse_json(
        run(
            emit("hello", logger="aidial_sdk", level="info", set_level=False),
            env={"DIAL_SDK_LOG_FORMAT": "json", "DIAL_SDK_LOG": "INFO"},
            telemetry=_TRACING_NO_CORRELATION,
        )
    )
    # No active span → all IDs are 0/False; service name always present.
    assert obj["message"] == "hello"
    assert obj["otelTraceID"] == "0"
    assert obj["otelSpanID"] == "0"
    assert obj["otelTraceSampled"] is False
    assert "otelServiceName" in obj


def test_json_template_referencing_otel_field_suppresses_auto_added_copy():
    obj = parse_json(
        run(
            emit("hello", logger="aidial_sdk", level="info", set_level=False),
            env={
                "DIAL_SDK_LOG_FORMAT": "json",
                "DIAL_SDK_LOG": "INFO",
                "DIAL_SDK_JSON_LOG_FORMAT": '{"msg":"%(message)s","trace_id":"%(otelTraceID)s"}',
            },
            telemetry=_TRACING_NO_CORRELATION,
        )
    )
    assert obj["trace_id"] == "0"  # renamed
    assert "otelTraceID" not in obj  # auto-added copy suppressed
    assert obj["otelSpanID"] == "0"  # other otel* fields still auto-added


# ---------------------------------------------------------------------------
# §2 — OTel log correlation (trace context injected into text)
# ---------------------------------------------------------------------------

# TracingConfig(logging=True) alone (no OTEL_PYTHON_LOG_CORRELATION env) must
# drive set_logging_format, proving the config field is wired.
_CORRELATION = "TelemetryConfig(tracing=TracingConfig(logging=True), logs=None, metrics=None)"


def test_correlation_uses_otel_default_format():
    lines = run(emit("hello"), telemetry=_CORRELATION)
    assert len(lines) == 1
    # Default OTel template: [name] ... [trace_id=... span_id=...] - message
    assert "[app]" in lines[0]
    assert "trace_id=0 span_id=0" in lines[0]
    assert lines[0].endswith("- hello")


def test_correlation_format_is_overridable():
    lines = run(
        emit("hello"),
        telemetry=_CORRELATION,
        env={
            "OTEL_PYTHON_LOG_FORMAT": "OTELFMT %(levelname)s trace=%(otelTraceID)s %(message)s"
        },
    )
    assert lines == ["OTELFMT WARNING trace=0 hello"]


def test_correlation_env_var_requires_traces_exporter():
    # OTEL_PYTHON_LOG_CORRELATION alone is a no-op: without OTEL_TRACES_EXPORTER
    # TelemetryConfig builds no TracingConfig, so §1's formatter stays in charge.
    lines = run(
        emit("hello", logger="aidial_sdk"),
        env={"OTEL_PYTHON_LOG_CORRELATION": "true"},
        telemetry="TelemetryConfig()",
    )
    assert len(lines) == 1
    assert "| aidial_sdk |" in lines[0] and lines[0].endswith("| hello")
    assert "trace_id=" not in lines[0]


def test_correlation_env_var_with_traces_exporter_enables_correlation():
    lines = run(
        emit("hello"),
        env={
            "OTEL_PYTHON_LOG_CORRELATION": "true",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_PYTHON_LOG_FORMAT": "OTELFMT %(levelname)s trace=%(otelTraceID)s %(message)s",
        },
        telemetry="TelemetryConfig()",
    )
    assert lines == ["OTELFMT WARNING trace=0 hello"]


def test_correlation_takes_over_third_party_handler():
    # openai grabs a root stderr handler at import (OPENAI_LOG=debug); correlation
    # must remove it so records render in OTel's format, not openai's "- app:NN -".
    lines = run(
        emit("hello"),
        preamble="import openai  # grabs root stderr handler on import",
        telemetry=_CORRELATION,
        env={
            "OPENAI_LOG": "debug",
            "OTEL_PYTHON_LOG_FORMAT": "OTELFMT %(levelname)s trace=%(otelTraceID)s %(message)s",
        },
    )
    assert lines == ["OTELFMT WARNING trace=0 hello"]
    assert not any("- app:" in ln for ln in lines)  # openai's format is gone


# ---------------------------------------------------------------------------
# §3 — OTel log export (OTEL_LOGS_EXPORTER=console)
# ---------------------------------------------------------------------------

_CONSOLE_ENV = {"OTEL_LOGS_EXPORTER": "console"}


def test_console_export_emits_one_compact_json_object():
    obj = parse_json(
        run(
            emit("hello", logger="app", level="info"),
            env=_CONSOLE_ENV,
            telemetry="TelemetryConfig()",
        )
    )
    assert obj["body"] == "hello"
    assert obj["severity_text"] == "INFO"


def test_console_export_honors_per_logger_debug_level():
    # The OTel handler must not impose a level floor over the app's own choice.
    obj = parse_json(
        run(
            emit("hello", logger="app", level="debug"),
            env=_CONSOLE_ENV,
            telemetry="TelemetryConfig()",
        )
    )
    assert obj["body"] == "hello"
    assert obj["severity_text"] == "DEBUG"


def test_console_export_replaces_competing_stderr_handler():
    # A pre-existing plain stderr handler on root must be dropped for the OTel one.
    obj = parse_json(
        run(
            emit("hello", logger="app"),
            preamble=(
                "import logging, sys\n"
                "_h = logging.StreamHandler(sys.stderr)\n"
                "_h.setFormatter(logging.Formatter('PLAIN %(message)s'))\n"
                "logging.getLogger().addHandler(_h)"
            ),
            env=_CONSOLE_ENV,
            telemetry="TelemetryConfig()",
        )
    )
    assert (
        obj["body"] == "hello"
    )  # single OTel line; "PLAIN hello" never emitted


def test_console_export_ignores_dial_sdk_format_vars():
    # With console export on, DIAL_SDK_* formatting is ignored — even the SDK's own
    # logger emits OTel JSON, not the SDK's {"level":..,"message":..} shape.
    obj = parse_json(
        run(
            emit("hello", logger="aidial_sdk", level="info", set_level=False),
            env={
                **_CONSOLE_ENV,
                "DIAL_SDK_LOG_FORMAT": "json",
                "DIAL_SDK_LOG": "INFO",
            },
            telemetry="TelemetryConfig()",
        )
    )
    assert obj["body"] == "hello"  # OTel shape
    assert "message" not in obj  # not the SDK JSON formatter


def test_console_export_with_tracing_emits_no_duplicates():
    # The OTel logging instrumentor installs a log handler of its own
    # (as of opentelemetry-instrumentation 0.61b0), which would export
    # every record a second time on top of the SDK's own handler.
    obj = parse_json(  # asserts a single line
        run(
            emit("hello", logger="app", level="info"),
            env=_CONSOLE_ENV,
            telemetry="TelemetryConfig(tracing=TracingConfig(logging=False), logs=LogsConfig(), metrics=None)",
        )
    )
    assert obj["body"] == "hello"


def test_console_export_wins_over_correlation_format():
    # §3 takes over stderr, so §2's text format must not be installed on top.
    obj = parse_json(  # asserts a single line
        run(
            emit("hello", logger="app", level="info"),
            env=_CONSOLE_ENV,
            telemetry="TelemetryConfig(tracing=TracingConfig(logging=True), logs=LogsConfig(), metrics=None)",
        )
    )
    assert obj["body"] == "hello"


# ---------------------------------------------------------------------------
# Extending the active mode to app loggers via configure_root_logger()
# ---------------------------------------------------------------------------


def test_configure_root_logger_renders_app_loggers_in_sdk_format():
    # §1: an app logger flows through the SDK's console handler.
    lines = run(
        emit("hello", logger="my-app", level="info"),
        root_logger=True,
    )
    assert len(lines) == 1
    assert "| my-app |" in lines[0]
    assert lines[0].endswith("| hello")


def test_configure_root_logger_takes_over_third_party_handler():
    # §1: openai's root stderr handler is dropped, so its records render in the
    # SDK format instead of openai's "- app:NN -".
    lines = run(
        emit("hello", logger="app"),
        preamble="import openai  # grabs root stderr handler on import",
        root_logger=True,
        env={"OPENAI_LOG": "debug"},
    )
    assert len(lines) == 1
    assert "| app |" in lines[0] and lines[0].endswith("| hello")
    assert "- app:" not in lines[0]


def test_configure_root_logger_defers_to_otel_export():
    # §3: configure_root_logger installs no competing handler; app loggers flow
    # through the OTel pipeline OTel already installed.
    obj = parse_json(
        run(
            emit("hello", logger="my-app"),
            env=_CONSOLE_ENV,
            telemetry="TelemetryConfig()",
            root_logger=True,
        )
    )
    assert obj["body"] == "hello"
