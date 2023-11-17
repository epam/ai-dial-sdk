from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
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
from opentelemetry.instrumentation.urllib import URLLibInstrumentor
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider
from prometheus_client import start_http_server

from aidial_sdk.telemetry.types import TelemetryConfig
from aidial_sdk.utils.logging import logger


def init_telemetry(
    app: FastAPI,
    config: TelemetryConfig,
):
    resource = Resource(attributes={SERVICE_NAME: config.service_name})

    if config.tracing is not None:
        tracer_provider = TracerProvider(resource=resource)

        if config.tracing.oltp_export:
            tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter())
            )

        set_tracer_provider(tracer_provider)

        RequestsInstrumentor().instrument()
        AioHttpClientInstrumentor().instrument()
        URLLibInstrumentor().instrument()

        if config.tracing.logging:
            LoggingInstrumentor().instrument(
                set_logging_format=True,
                log_level=logger.getEffectiveLevel(),
            )

    if config.metrics is not None:
        set_meter_provider(
            MeterProvider(
                resource=resource, metric_readers=[PrometheusMetricReader()]
            )
        )

        SystemMetricsInstrumentor().instrument()

        start_http_server(port=config.metrics.port)

    if config.tracing is not None or config.metrics is not None:
        # FastAPI instrumentor reports both metrics and traces
        FastAPIInstrumentor.instrument_app(app)
