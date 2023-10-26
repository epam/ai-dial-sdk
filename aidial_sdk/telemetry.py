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
from starlette_exporter import handle_metrics


def init_telemetry(
    app: FastAPI,
    service_name: str,
    enable_oltp_export: bool,
):
    resource = Resource(attributes={SERVICE_NAME: service_name})

    tracer_provider = TracerProvider(resource=resource)

    if enable_oltp_export:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter())
        )

    set_tracer_provider(tracer_provider)

    app.add_route("/metrics", handle_metrics)

    set_meter_provider(
        MeterProvider(
            resource=resource, metric_readers=[PrometheusMetricReader()]
        )
    )

    LoggingInstrumentor().instrument(set_logging_format=True)
    FastAPIInstrumentor.instrument_app(app)
    RequestsInstrumentor().instrument()
    AioHttpClientInstrumentor().instrument()
    URLLibInstrumentor().instrument()
    SystemMetricsInstrumentor().instrument()
