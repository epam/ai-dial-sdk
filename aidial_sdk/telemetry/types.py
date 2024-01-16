from typing import Optional

from pydantic import BaseModel


class TracingConfig(BaseModel):
    otlp_export: bool = False
    logging: bool = False


class MetricsConfig(BaseModel):
    port: int = 9464


class TelemetryConfig(BaseModel):
    service_name: Optional[str] = None
    tracing: Optional[TracingConfig] = None
    metrics: Optional[MetricsConfig] = None
