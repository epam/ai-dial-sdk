from typing import Optional

from aidial_sdk.pydantic_v1 import BaseModel


class TracingConfig(BaseModel):
    otlp_export: bool = False
    logging: bool = False


class MetricsConfig(BaseModel):
    port: int = 9464


class TelemetryConfig(BaseModel):
    service_name: Optional[str] = None
    tracing: Optional[TracingConfig] = None
    metrics: Optional[MetricsConfig] = None
