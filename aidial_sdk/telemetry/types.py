from typing import Optional

from pydantic import BaseModel


class TracingConfig(BaseModel):
    oltp_export: bool = False
    logging: bool = False


class MetricsConfig(BaseModel):
    pass


class TelemetryConfig(BaseModel):
    service_name: str
    tracing: Optional[TracingConfig] = None
    metrics: Optional[MetricsConfig] = None
