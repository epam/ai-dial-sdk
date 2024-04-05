import logging

from fastapi import FastAPI
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.aiohttp_client import (
    AioHttpClientInstrumentor,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.system_metrics import (
    SystemMetricsInstrumentor,
)
from opentelemetry.instrumentation.urllib import URLLibInstrumentor
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics._internal.export import (
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider
from prometheus_client import start_http_server

from aidial_sdk.telemetry.types import TelemetryConfig


def init_telemetry(
    app: FastAPI,
    config: TelemetryConfig,
):
    resource = Resource.create(
        attributes=(
            {SERVICE_NAME: config.service_name} if config.service_name else None
        )
    )

    if config.tracing is not None:
        tracer_provider = TracerProvider(resource=resource)

        if config.tracing.otlp_export:
            tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter())
            )

        set_tracer_provider(tracer_provider)

        RequestsInstrumentor().instrument()
        AioHttpClientInstrumentor().instrument()
        URLLibInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()

        if config.tracing.logging:
            # Setting the root logger format in order to include
            # tracing information: span_id, trace_id
            LoggingInstrumentor().instrument(set_logging_format=True)

    if config.logs is not None:
        # Adding a handler to the root logger which exports the logs to OTLP
        provider = LoggerProvider(resource=resource)

        if config.logs.otlp_export:
            provider.add_log_record_processor(
                BatchLogRecordProcessor(OTLPLogExporter())
            )

        set_logger_provider(provider)

        handler = LoggingHandler(level=config.logs.level)
        logging.getLogger().addHandler(handler)

    if config.metrics is not None:
        metric_readers = []

        if config.metrics.prometheus_export:
            metric_readers.append(PrometheusMetricReader())

        if config.metrics.otlp_export:
            metric_readers.append(
                PeriodicExportingMetricReader(OTLPMetricExporter())
            )

        set_meter_provider(
            MeterProvider(resource=resource, metric_readers=metric_readers)
        )

        SystemMetricsInstrumentor().instrument()

        if config.metrics.prometheus_export:
            start_http_server(port=config.metrics.port)

    if config.tracing is not None or config.metrics is not None:
        # FastAPI instrumentor reports both metrics and traces
        FastAPIInstrumentor.instrument_app(app)
