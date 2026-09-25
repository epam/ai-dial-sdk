import logging
import os
from typing import Literal, get_args

from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.utils.env import env_var_list

ExcludableASGISpan = Literal["receive", "send"]

# OpenTelemetry SDK configuration env vars:
# https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/

OTEL_LOGS_EXPORTER = env_var_list("OTEL_LOGS_EXPORTER")
OTEL_TRACES_EXPORTER = env_var_list("OTEL_TRACES_EXPORTER")
OTEL_METRICS_EXPORTER = env_var_list("OTEL_METRICS_EXPORTER")
OTEL_EXPORTER_PROMETHEUS_PORT = int(
    os.getenv("OTEL_EXPORTER_PROMETHEUS_PORT", 9464)
)
OTEL_PYTHON_LOG_CORRELATION = (
    os.getenv("OTEL_PYTHON_LOG_CORRELATION", "false").lower() == "true"
)
# Which ASGI lifecycle sub-spans the FastAPI instrumentation should not emit:
# a comma-separated subset of `receive,send`. Empty by default, which keeps
# emitting both.
#
# The instrumentation opens one span per ASGI message, so for a streaming
# deployment `send` means one span per streamed chunk -- on a long completion
# that is thousands of spans carrying nothing the request span doesn't
# already say, and the cost of building and exporting them falls on the
# event loop.
#
# The name matches the one proposed upstream in
# open-telemetry/opentelemetry-python-contrib#3992, so that if the
# instrumentation grows its own support for this variable, the same
# configuration keeps working and this handling can simply be dropped.
OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS = env_var_list(
    "OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS"
)


def _parse_excluded_asgi_spans() -> list[ExcludableASGISpan]:
    allowed = get_args(ExcludableASGISpan)
    return [
        span
        for raw in OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS
        if (span := raw.strip().lower()) in allowed
    ]


class LogsConfig(BaseModel):
    otlp_export: bool = "otlp" in OTEL_LOGS_EXPORTER
    console_export: bool = "console" in OTEL_LOGS_EXPORTER

    level: int = logging.INFO
    """Deprecated and ignored: the log handler no longer imposes a level floor;
    set per-logger levels instead. See docs/logging.md."""


class TracingConfig(BaseModel):
    otlp_export: bool = "otlp" in OTEL_TRACES_EXPORTER
    logging: bool = OTEL_PYTHON_LOG_CORRELATION
    excluded_asgi_spans: list[ExcludableASGISpan] = _parse_excluded_asgi_spans()


class MetricsConfig(BaseModel):
    otlp_export: bool = "otlp" in OTEL_METRICS_EXPORTER
    prometheus_export: bool = "prometheus" in OTEL_METRICS_EXPORTER
    port: int = OTEL_EXPORTER_PROMETHEUS_PORT


class TelemetryConfig(BaseModel):
    service_name: str | None = None

    logs: LogsConfig | None = LogsConfig() if OTEL_LOGS_EXPORTER else None
    tracing: TracingConfig | None = (
        TracingConfig() if OTEL_TRACES_EXPORTER else None
    )
    metrics: MetricsConfig | None = (
        MetricsConfig() if OTEL_METRICS_EXPORTER else None
    )

    def is_noop(self):
        return (
            self.logs is None and self.tracing is None and self.metrics is None
        )
