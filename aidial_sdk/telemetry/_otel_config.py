import os

from opentelemetry.configuration import OpenTelemetryConfiguration
from opentelemetry.configuration import models as otel
from opentelemetry.sdk.environment_variables import (
    OTEL_BLRP_EXPORT_TIMEOUT,
    OTEL_BLRP_MAX_EXPORT_BATCH_SIZE,
    OTEL_BLRP_MAX_QUEUE_SIZE,
    OTEL_BLRP_SCHEDULE_DELAY,
    OTEL_METRIC_EXPORT_INTERVAL,
    OTEL_METRIC_EXPORT_TIMEOUT,
    OTEL_RESOURCE_ATTRIBUTES,
    OTEL_SERVICE_NAME,
)
from opentelemetry.sdk.resources import SERVICE_NAME

from aidial_sdk.telemetry.types import TelemetryConfig
from aidial_sdk.utils.env import env_int


def to_otel_config(config: TelemetryConfig) -> OpenTelemetryConfiguration:
    instrumentors: dict[str, dict] = {}

    tracer_provider = None
    if config.tracing is not None:
        processors = []
        if config.tracing.otlp_export:
            processors.append(
                otel.SpanProcessor(
                    batch=otel.BatchSpanProcessor(
                        exporter=otel.SpanExporter(
                            otlp_grpc=otel.OtlpGrpcExporter()
                        )
                    )
                )
            )
        tracer_provider = otel.TracerProvider(processors=processors)

        instrumentors["logging"] = {
            "set_logging_format": config.tracing.logging,
            "inject_trace_context": True,
        }

    logger_provider = None
    if config.logs is not None:
        processors = []
        if config.logs.otlp_export:
            processors.append(
                otel.LogRecordProcessor(
                    batch=otel.BatchLogRecordProcessor(
                        exporter=otel.LogRecordExporter(
                            otlp_grpc=otel.OtlpGrpcExporter()
                        ),
                        schedule_delay=env_int(OTEL_BLRP_SCHEDULE_DELAY),
                        export_timeout=env_int(OTEL_BLRP_EXPORT_TIMEOUT),
                        max_queue_size=env_int(OTEL_BLRP_MAX_QUEUE_SIZE),
                        max_export_batch_size=env_int(
                            OTEL_BLRP_MAX_EXPORT_BATCH_SIZE
                        ),
                    )
                )
            )
        if config.logs.console_export:
            processors.append(
                otel.LogRecordProcessor(
                    simple=otel.SimpleLogRecordProcessor(
                        exporter=otel.LogRecordExporter(console={})
                    )
                )
            )
        logger_provider = otel.LoggerProvider(processors=processors)

    meter_provider = None
    if config.metrics is not None:
        readers = []
        if config.metrics.prometheus_export:
            readers.append(
                otel.MetricReader(
                    pull=otel.PullMetricReader(
                        exporter=otel.PullMetricExporter(
                            prometheus_development=otel.ExperimentalPrometheusMetricExporter(
                                # When not set, the host is defaulted to 'localhost', # which nothing outside the container could scrape.
                                host="0.0.0.0",  # noqa: S104
                                port=config.metrics.port,
                            )
                        )
                    )
                )
            )
        if config.metrics.otlp_export:
            readers.append(
                otel.MetricReader(
                    periodic=otel.PeriodicMetricReader(
                        exporter=otel.PushMetricExporter(
                            otlp_grpc=otel.OtlpGrpcMetricExporter()
                        ),
                        interval=env_int(OTEL_METRIC_EXPORT_INTERVAL),
                        timeout=env_int(OTEL_METRIC_EXPORT_TIMEOUT),
                    )
                )
            )
        meter_provider = otel.MeterProvider(readers=readers)

    return OpenTelemetryConfiguration(
        # Only load_config_file() validates the version,
        # but the model still needs one, as the field is required.
        file_format="dummy-version",
        resource=_to_resource(config.service_name),
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
        instrumentation_development=(
            otel.ExperimentalInstrumentation(python=instrumentors)
            if instrumentors
            else None
        ),
    )


def _to_resource(service_name: str | None) -> otel.Resource:
    name = service_name or os.getenv(OTEL_SERVICE_NAME)
    return otel.Resource(
        attributes=(
            [otel.AttributeNameValue(name=SERVICE_NAME, value=name)]
            if name
            else None
        ),
        attributes_list=os.getenv(OTEL_RESOURCE_ATTRIBUTES),
    )
