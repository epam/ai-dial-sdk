"""TelemetryConfig -> OpenTelemetryConfiguration, the generated half of the
telemetry setup. The declarative model ignores parts of the environment that
the SDK used to honor, so the generator passes them explicitly."""

from aidial_sdk.telemetry._otel_config import to_otel_config
from aidial_sdk.telemetry.init import _enrich_configuration
from aidial_sdk.telemetry.types import (
    LogsConfig,
    MetricsConfig,
    TelemetryConfig,
    TracingConfig,
)
from tests.test_telemetry_logs import run

_PROBE_APP = (
    "from starlette.testclient import TestClient\n"
    "from opentelemetry import trace\n"
    "from aidial_sdk import DIALApp\n"
    "from aidial_sdk.telemetry.types import TelemetryConfig, TracingConfig\n"
    "app = DIALApp(telemetry_config=TelemetryConfig("
    "tracing=TracingConfig(otlp_export=False)), add_healthcheck=True)\n"
    "@app.get('/probe')\n"
    "def probe():\n"
    "    ctx = trace.get_current_span().get_span_context()\n"
    "    return {'trace_id': format(ctx.trace_id, '032x')}\n"
    "r = TestClient(app).get('/probe', headers={'traceparent': "
    "'00-11111111111111111111111111111111-2222222222222222-01'})\n"
    "print(r.status_code, r.json()['trace_id'])"
)

_INCOMING_TRACE_ID = "1" * 32


def test_no_signal_is_configured_by_default():
    conf = to_otel_config(TelemetryConfig())
    assert conf.tracer_provider is None
    assert conf.logger_provider is None
    assert conf.meter_provider is None
    assert conf.instrumentation_development is None


def test_resource_is_taken_from_the_environment(monkeypatch):
    # create_resource() reads neither of these on its own.
    monkeypatch.setenv("OTEL_SERVICE_NAME", "from-env")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "team=dial")

    resource = to_otel_config(TelemetryConfig()).resource
    assert resource is not None
    assert resource.attributes_list == "team=dial"
    assert [(a.name, a.value) for a in resource.attributes or []] == [
        ("service.name", "from-env")
    ]

    # An explicit service name wins over the variable.
    resource = to_otel_config(TelemetryConfig(service_name="explicit")).resource
    assert resource is not None
    assert [a.value for a in resource.attributes or []] == ["explicit"]


def test_propagators_are_left_out_of_the_configuration():
    # Saying nothing keeps OTEL_PROPAGATORS in charge: init_telemetry restores
    # what it had loaded, which configure_sdk() resets.
    assert to_otel_config(TelemetryConfig()).propagator is None


def test_prometheus_is_reachable_from_outside_the_container():
    conf = to_otel_config(
        TelemetryConfig(
            metrics=MetricsConfig(prometheus_export=True, port=1234)
        )
    )
    assert conf.meter_provider is not None
    pull = conf.meter_provider.readers[0].pull
    assert pull is not None
    exporter = pull.exporter.prometheus_development
    assert exporter is not None
    # The declarative default of localhost would be scrapeable by nothing.
    assert (exporter.host, exporter.port) == ("0.0.0.0", 1234)  # noqa: S104


def test_batching_still_honors_its_environment(monkeypatch):
    # The factory substitutes explicit defaults for the unset fields.
    monkeypatch.setenv("OTEL_BLRP_SCHEDULE_DELAY", "42")
    monkeypatch.setenv("OTEL_METRIC_EXPORT_INTERVAL", "17")

    conf = to_otel_config(
        TelemetryConfig(
            logs=LogsConfig(otlp_export=True),
            metrics=MetricsConfig(otlp_export=True),
        )
    )
    assert conf.logger_provider is not None
    batch = conf.logger_provider.processors[0].batch
    assert batch is not None and batch.schedule_delay == 42

    assert conf.meter_provider is not None
    periodic = conf.meter_provider.readers[0].periodic
    assert periodic is not None and periodic.interval == 17


def test_incoming_trace_context_is_continued():
    # The traceparent of the request must land on the server span, or the app
    # silently starts a trace of its own.
    assert run(_PROBE_APP, capture="stdout") == [f"200 {_INCOMING_TRACE_ID}"]


def test_tracing_instruments_the_installed_http_clients():
    conf = to_otel_config(TelemetryConfig(tracing=TracingConfig()))
    _enrich_configuration(conf)

    assert conf.instrumentation_development is not None
    python = conf.instrumentation_development.python or {}
    assert python == {
        "aiohttp-client": {},
        "httpx": {},
        "requests": {},
        "urllib": {},
        "logging": {
            "inject_trace_context": True,
            "set_logging_format": False,
            "enable_log_auto_instrumentation": False,
        },
    }
