"""OTEL_CONFIG_FILE: the OTel declarative configuration file.

When it is set, the file is the sole source of the OpenTelemetry setup:
TelemetryConfig and the OTEL_* variables are ignored.
"""

import pytest

from tests.test_telemetry_logs import emit, parse_json, run

_LOGS_TO_CONSOLE = """
file_format: "1.0-rc.1"
resource:
  attributes:
    - name: service.name
      value: app-from-file
logger_provider:
  processors:
    - simple:
        exporter:
          console: {}
"""

_LOG_CORRELATION = """
file_format: "1.0-rc.1"
instrumentation/development:
  python:
    logging:
      set_logging_format: true
"""

_TRACES_TO_CONSOLE = """
file_format: "1.0-rc.1"
tracer_provider:
  processors:
    - simple:
        exporter:
          console: {}
"""

# An empty TelemetryConfig is all the opt-in the file needs.
_CREATE_APP = (
    "from aidial_sdk import DIALApp\n"
    "from aidial_sdk.telemetry.types import TelemetryConfig\n"
    "app = DIALApp(telemetry_config=TelemetryConfig(), add_healthcheck=True)\n"
)


@pytest.fixture
def config_file(tmp_path):
    def create(content: str) -> dict[str, str]:
        path = tmp_path / "otel.yaml"
        path.write_text(content)
        return {"OTEL_CONFIG_FILE": str(path)}

    return create


def test_config_file_alone_configures_log_export(config_file):
    # Rendered as §3: the compact one-line shape of the SDK, on stderr.
    record = parse_json(
        run(
            _CREATE_APP + emit("hello", level="info"),
            env=config_file(_LOGS_TO_CONSOLE),
        )
    )
    assert record["body"] == "hello"
    assert record["resource"]["attributes"]["service.name"] == "app-from-file"


def test_config_file_log_export_takes_over_the_console(config_file):
    # A single record: the stderr handler of the SDK is dropped for the OTel
    # one, rather than logging its own rendering next to it.
    record = parse_json(
        run(
            _CREATE_APP + emit("hello", logger="aidial_sdk", level="info"),
            env=config_file(_LOGS_TO_CONSOLE),
        )
    )
    assert record["body"] == "hello"


def test_config_file_requires_a_telemetry_config(config_file):
    # Telemetry stays opt-in: no TelemetryConfig, no OTel — §1 formatting.
    lines = run(
        "from aidial_sdk import DIALApp\nDIALApp()\n"
        + emit("hello", logger="aidial_sdk"),
        env=config_file(_LOGS_TO_CONSOLE),
    )
    assert len(lines) == 1 and lines[0].endswith("| hello")


def test_config_file_supersedes_the_env_vars(config_file):
    # Both would export to the console; the record is exported once, by the
    # provider the file configured — named after it.
    record = parse_json(
        run(
            _CREATE_APP + emit("hello", level="info"),
            env={
                **config_file(_LOGS_TO_CONSOLE),
                "OTEL_LOGS_EXPORTER": "console",
            },
        )
    )
    assert record["resource"]["attributes"]["service.name"] == "app-from-file"


def test_config_file_can_enable_log_correlation(config_file):
    # §2 from the file: the instrumentor reformats the console, so the SDK's
    # own handler has to step aside first.
    lines = run(
        _CREATE_APP + emit("hello"),
        env={
            **config_file(_LOG_CORRELATION),
            "OTEL_PYTHON_LOG_FORMAT": "OTELFMT %(levelname)s trace=%(otelTraceID)s %(message)s",
        },
    )
    assert lines == ["OTELFMT WARNING trace=0 hello"]


def test_config_file_traces_requests(config_file):
    # The app is created before the file is read, so it needs instrumenting
    # explicitly; a config file without propagators must not break requests.
    lines = run(
        _CREATE_APP
        + "from starlette.testclient import TestClient\n"
        + "print('STATUS', TestClient(app).get('/health').status_code)",
        env=config_file(_TRACES_TO_CONSOLE),
        capture="stdout",
    )
    assert "STATUS 200" in lines
    assert any('"name": "GET /health"' in ln for ln in lines)
