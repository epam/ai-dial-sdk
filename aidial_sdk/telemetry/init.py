import logging
import os
import sys
from importlib.util import find_spec

from fastapi import FastAPI
from opentelemetry.configuration import (
    OpenTelemetryConfiguration,
    configure_sdk,
    load_config_file,
)
from opentelemetry.configuration import models as otel
from opentelemetry.environment_variables import OTEL_PROPAGATORS
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggingHandler

from aidial_sdk.telemetry._otel_config import to_otel_config
from aidial_sdk.telemetry.types import TelemetryConfig, get_otel_config_file
from aidial_sdk.utils._logging import remove_stream_handlers
from aidial_sdk.utils.log_config import route_sdk_loggers_to_root

_HTTP_CLIENT_INSTRUMENTORS = {
    "requests": "opentelemetry.instrumentation.requests",
    "aiohttp-client": "opentelemetry.instrumentation.aiohttp_client",
    "urllib": "opentelemetry.instrumentation.urllib",
    "httpx": "opentelemetry.instrumentation.httpx",
}


def init_telemetry(app: FastAPI | None, config: TelemetryConfig) -> None:
    config_file = get_otel_config_file()

    conf = (
        load_config_file(config_file) if config_file else to_otel_config(config)
    )
    _apply_otel_config(app, conf)


def _apply_otel_config(
    app: FastAPI | None, conf: OpenTelemetryConfiguration
) -> None:
    if conf.disabled:
        configure_sdk(conf)  # logs why nothing was configured
        return

    _apply_dial_specifics(conf)
    configure_sdk(conf)

    if _takes_over_console(conf):
        # Remove any competing handlers to avoid duplicate logging. The SDK
        # loggers are rerouted as well: a configuration file is unknown to
        # configure_sdk_logger() at import time, and log correlation enabled
        # through TelemetryConfig alone is invisible to it too.
        remove_stream_handlers(logging.getLogger(), sys.stderr)
        route_sdk_loggers_to_root()

    if conf.logger_provider is not None:
        logging.getLogger().addHandler(LoggingHandler())

    if app and (conf.tracer_provider or conf.meter_provider):
        FastAPIInstrumentor.instrument_app(app)


def _apply_dial_specifics(conf: OpenTelemetryConfiguration) -> None:
    """Extra configuration specific for DIAL SDK"""

    # Default propagation
    conf.propagator = conf.propagator or otel.Propagator(
        composite_list=os.getenv(OTEL_PROPAGATORS, "tracecontext,baggage")
    )

    # Replacing the default console exporter with the one that prints JSON in a single line
    def _patch_exporter(exporter: otel.LogRecordExporter):
        if exporter.console == {}:
            exporter.console = None
            exporter.additional_properties["one_line_logs_exporter"] = {}

    if provider := conf.logger_provider:
        for processor in provider.processors:
            if proc := processor.batch:
                _patch_exporter(proc.exporter)
            if proc := processor.simple:
                _patch_exporter(proc.exporter)

    # Adding the default HTTP client instrumentors
    instr = {}
    if conf.instrumentation_development:
        instr = conf.instrumentation_development.python or {}

    for name, module in _HTTP_CLIENT_INSTRUMENTORS.items():
        if find_spec(module):
            instr[name] = instr.get(name) or {}

    if conf.meter_provider:
        instr["system_metrics"] = instr.get("system_metrics") or {}

    conf.instrumentation_development = otel.ExperimentalInstrumentation(
        python=instr
    )


def _takes_over_console(conf: OpenTelemetryConfiguration) -> bool:
    logger_provider = conf.logger_provider
    for processor in (logger_provider and logger_provider.processors) or []:
        exporting = processor.batch or processor.simple
        if exporting and exporting.exporter.console is not None:
            return True

    instrumentation = conf.instrumentation_development
    python = (instrumentation and instrumentation.python) or {}
    # The logging instrumentor reformats the root handler via basicConfig(),
    # which is a no-op unless the console is free by the time it runs.
    return bool((python.get("logging") or {}).get("set_logging_format"))
