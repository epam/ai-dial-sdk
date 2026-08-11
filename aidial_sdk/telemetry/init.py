import logging
import os
import sys
from importlib.util import find_spec

from fastapi import FastAPI
from opentelemetry.configuration import (
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

otel_owns_console = False
"""Whether OTel has been handed the console handler of the root logger, set
below once the configuration is known to claim it. Consulted by
configure_root_logger(), which cannot tell from the environment alone: telemetry
stays opt-in through DIALApp(telemetry_config=...) and a configuration file may
say otherwise."""

_ONE_LINE_LOGS_EXPORTER = "one_line_logs_exporter"

_HTTP_CLIENT_INSTRUMENTORS = {
    "requests": "opentelemetry.instrumentation.requests",
    "aiohttp-client": "opentelemetry.instrumentation.aiohttp_client",
    "urllib": "opentelemetry.instrumentation.urllib",
    "httpx": "opentelemetry.instrumentation.httpx",
}


def init_telemetry(app: FastAPI | None, config: TelemetryConfig) -> None:
    if file := get_otel_config_file():
        otel_config = load_config_file(file)
    else:
        otel_config = to_otel_config(config)

    _apply_otel_config(app, otel_config)


def _apply_otel_config(
    app: FastAPI | None, config: otel.OpenTelemetryConfiguration
) -> None:
    if config.disabled:
        configure_sdk(config)  # logs why nothing was configured
        return

    _enrich_configuration(config)

    if _takes_over_console(config):
        # Free the console *before* configure_sdk(), since the logging
        # instrumentor only reformats the root handler when it may install it
        # itself. Removing any competing handlers also avoids duplicate logging.
        # The SDK loggers are rerouted as well: a configuration file is unknown
        # to configure_sdk_logger() at import time, and log correlation enabled
        # through TelemetryConfig alone is invisible to it too.
        global otel_owns_console
        otel_owns_console = True
        remove_stream_handlers(logging.getLogger(), sys.stderr)
        route_sdk_loggers_to_root()

    if config.logger_provider is not None:
        logging.getLogger().addHandler(LoggingHandler())

    if app and (config.tracer_provider or config.meter_provider):
        FastAPIInstrumentor.instrument_app(app)

    configure_sdk(config)


def _enrich_configuration(config: otel.OpenTelemetryConfiguration) -> None:
    """Extra configuration specific for the DIAL SDK"""

    # 1. Set the default propagators
    config.propagator = config.propagator or otel.Propagator(
        composite_list=os.getenv(OTEL_PROPAGATORS, "tracecontext,baggage")
    )

    # 2. Replace the default console exporter with the one
    # that prints JSON in a single line
    def _patch_exporter(exporter: otel.LogRecordExporter):
        if exporter.console == {}:
            exporter.console = None
            exporter.additional_properties[_ONE_LINE_LOGS_EXPORTER] = {}

    if provider := config.logger_provider:
        for processor in provider.processors:
            if proc := processor.batch:
                _patch_exporter(proc.exporter)
            if proc := processor.simple:
                _patch_exporter(proc.exporter)

    # 3. Add the default instrumentors for HTTP clients and system metrics.
    # The instrumentation of other languages, if any, is left untouched.
    instrumentation = (
        config.instrumentation_development or otel.ExperimentalInstrumentation()
    )
    instr = instrumentation.python or {}

    if config.tracer_provider:
        for name, module in _HTTP_CLIENT_INSTRUMENTORS.items():
            if find_spec(module):
                instr[name] = instr.get(name) or {}

    if config.meter_provider:
        instr["system_metrics"] = instr.get("system_metrics") or {}

    instrumentation.python = instr
    config.instrumentation_development = instrumentation


def _takes_over_console(conf: otel.OpenTelemetryConfiguration) -> bool:
    logger_provider = conf.logger_provider
    for processor in (logger_provider and logger_provider.processors) or []:
        for proc in (processor.batch, processor.simple):
            # An empty dict is the configured shape of both exporters,
            # so their presence is what to check, not their truthiness.
            if proc and (
                proc.exporter.console is not None
                or _ONE_LINE_LOGS_EXPORTER
                in proc.exporter.additional_properties
            ):
                return True

    instrumentation = conf.instrumentation_development
    python = (instrumentation and instrumentation.python) or {}
    # The logging instrumentor reformats the root handler via basicConfig(),
    # which is a no-op unless the console is free by the time it runs.
    return bool((python.get("logging") or {}).get("set_logging_format"))
