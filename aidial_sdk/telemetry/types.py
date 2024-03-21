import os
from typing import Optional

from aidial_sdk.pydantic_v1 import BaseModel

OTEL_LOGS_EXPORTER = os.getenv("OTEL_LOGS_EXPORTER", "").split(",")
OTEL_TRACES_EXPORTER = os.getenv("OTEL_TRACES_EXPORTER", "").split(",")
OTEL_METRICS_EXPORTER = os.getenv("OTEL_METRICS_EXPORTER", "").split(",")
OTEL_EXPORTER_PROMETHEUS_PORT = int(
    os.getenv("OTEL_EXPORTER_PROMETHEUS_PORT", 9464)
)


class LogsConfig(BaseModel):
    otlp_export: bool = "otlp" in OTEL_LOGS_EXPORTER


class TracingConfig(BaseModel):
    otlp_export: bool = "otlp" in OTEL_TRACES_EXPORTER

    """Add tracing information to the console logs"""
    logging: bool = False


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
