import os
from typing import Optional

from aidial_sdk.pydantic_v1 import BaseModel

# Variables borrowed from OpenTelemetry:
# https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/

OTEL_LOGS_EXPORTER = os.getenv("OTEL_LOGS_EXPORTER", "").split(",")
OTEL_TRACES_EXPORTER = os.getenv("OTEL_TRACES_EXPORTER", "").split(",")
OTEL_METRICS_EXPORTER = os.getenv("OTEL_METRICS_EXPORTER", "").split(",")
OTEL_EXPORTER_PROMETHEUS_PORT = int(
    os.getenv("OTEL_EXPORTER_PROMETHEUS_PORT", 9464)
)

# DIAL-specific env vars
DIAL_TELEMETRY_ADD_TRACES_TO_LOGS = (
    os.getenv("DIAL_TELEMETRY_ADD_TRACES_TO_LOGS", "false").lower() == "true"
)


class LogsConfig(BaseModel):
    otlp_export: bool = "otlp" in OTEL_LOGS_EXPORTER


class TracingConfig(BaseModel):
    otlp_export: bool = "otlp" in OTEL_TRACES_EXPORTER

    """Configure logging to include tracing information into a log message"""
    logging: bool = DIAL_TELEMETRY_ADD_TRACES_TO_LOGS


class MetricsConfig(BaseModel):
    otlp_export: bool = "otlp" in OTEL_METRICS_EXPORTER
    prometheus_export: bool = True
    port: int = OTEL_EXPORTER_PROMETHEUS_PORT


class TelemetryConfig(BaseModel):
    service_name: Optional[str] = None

    logs: Optional[LogsConfig] = LogsConfig() if OTEL_LOGS_EXPORTER else None
    tracing: Optional[TracingConfig] = (
        TracingConfig() if OTEL_TRACES_EXPORTER else None
    )
    metrics: Optional[MetricsConfig] = (
        MetricsConfig() if OTEL_METRICS_EXPORTER else None
    )
