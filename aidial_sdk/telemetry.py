from fastapi import FastAPI
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.aiohttp_client import (
    AioHttpClientInstrumentor,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.system_metrics import (
    SystemMetricsInstrumentor,
)
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from starlette_exporter import handle_metrics


def init_telemetry(app: FastAPI, service_name: str):
    app.add_route("/metrics", handle_metrics)

    set_meter_provider(
        MeterProvider(
            resource=Resource(attributes={SERVICE_NAME: service_name}),
            metric_readers=[PrometheusMetricReader()],
        )
    )

    FastAPIInstrumentor.instrument_app(app)
    RequestsInstrumentor().instrument()
    AioHttpClientInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    SystemMetricsInstrumentor().instrument()
