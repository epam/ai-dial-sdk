from typing import Optional

from aidial_sdk.pydantic_v1 import BaseModel


class TracingConfig(BaseModel):
    oltp_export: bool = False
    logging: bool = False


class MetricsConfig(BaseModel):
    port: int = 9464


class TelemetryConfig(BaseModel):
    service_name: str
    tracing: Optional[TracingConfig] = None
    metrics: Optional[MetricsConfig] = None
