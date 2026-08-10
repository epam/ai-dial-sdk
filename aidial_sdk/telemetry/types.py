import logging
import os

from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.utils.env import env_var_list

# OpenTelemetry SDK configuration env vars:
# https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/
#
# Spelled out rather than imported from opentelemetry.*: this module is loaded
# by DIALApp even when the telemetry extra is not installed.

OTEL_LOGS_EXPORTER = env_var_list("OTEL_LOGS_EXPORTER")
OTEL_TRACES_EXPORTER = env_var_list("OTEL_TRACES_EXPORTER")
OTEL_METRICS_EXPORTER = env_var_list("OTEL_METRICS_EXPORTER")
OTEL_EXPORTER_PROMETHEUS_PORT = int(
    os.getenv("OTEL_EXPORTER_PROMETHEUS_PORT", 9464)
)
OTEL_PYTHON_LOG_CORRELATION = (
    os.getenv("OTEL_PYTHON_LOG_CORRELATION", "false").lower() == "true"
)


def get_otel_config_file() -> str | None:
    """Path to the OTel declarative configuration file, if any.

    Read lazily, unlike the constants above: it decides whether telemetry is
    configured at all, so tests and embedders may set it after import."""
    return os.getenv("OTEL_CONFIG_FILE") or None


class LogsConfig(BaseModel):
    otlp_export: bool = "otlp" in OTEL_LOGS_EXPORTER
    console_export: bool = "console" in OTEL_LOGS_EXPORTER

    level: int = logging.INFO
    """Deprecated and ignored: the log handler no longer imposes a level floor;
    set per-logger levels instead. See docs/logging.md."""


class TracingConfig(BaseModel):
    otlp_export: bool = "otlp" in OTEL_TRACES_EXPORTER
    logging: bool = OTEL_PYTHON_LOG_CORRELATION


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
