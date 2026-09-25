# Telemetry

The SDK ships OpenTelemetry instrumentation for traces, metrics and logs. It emits **no spans or metrics of its own** — everything comes from instrumentors it installs on FastAPI, the HTTP clients and the host process. Nothing is enabled unless you both install the extra and ask for a signal.

```sh
pip install "aidial-sdk[telemetry]"
```

```python
from aidial_sdk import DIALApp
from aidial_sdk.telemetry.types import TelemetryConfig

app = DIALApp(telemetry_config=TelemetryConfig(service_name="my-app"))
```

That call on its own does nothing. Each of the three signals switches on only when its exporter variable is set:

| You want | Set |
| --- | --- |
| Traces, and client/server spans | `OTEL_TRACES_EXPORTER=otlp` |
| Metrics over OTLP | `OTEL_METRICS_EXPORTER=otlp` |
| Metrics on a Prometheus endpoint | `OTEL_METRICS_EXPORTER=prometheus` |
| Log records exported | `OTEL_LOGS_EXPORTER=otlp` — see [docs/logging.md](logging.md) |

With none of them set, `TelemetryConfig()` is a no-op and is safe to pass even without the extra installed.

## Environment variables

Required var in **bold**, optional (customization) vars in plain.

| Variable | Default | Purpose |
| --- | --- | --- |
| **`OTEL_TRACES_EXPORTER`** | unset | Comma-separated. `otlp` exports spans. Any value turns tracing on. |
| **`OTEL_METRICS_EXPORTER`** | unset | Comma-separated. `otlp`, `prometheus`, or both. |
| **`OTEL_LOGS_EXPORTER`** | unset | Comma-separated. `otlp`, `console`. See [docs/logging.md](logging.md). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | Collector address. Exporters are gRPC. |
| `OTEL_EXPORTER_PROMETHEUS_PORT` | `9464` | Port for the Prometheus endpoint. |
| `OTEL_SERVICE_NAME` | `unknown_service` | Used only when `service_name` is not set in code. |
| `OTEL_PYTHON_LOG_CORRELATION` | `false` | Injects trace and span IDs into console logs. |
| `OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS` | unset | Comma-separated subset of `receive,send`. Suppresses the ASGI lifecycle sub-spans. See [Streaming deployments](#streaming-deployments). |

All other OpenTelemetry SDK variables apply as normal, because the exporters are constructed with no arguments and read their own configuration from the environment — `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_METRIC_EXPORT_INTERVAL`, `OTEL_TRACES_SAMPLER` and `OTEL_RESOURCE_ATTRIBUTES` among them.

Two variables are worth calling out together. `OTEL_PYTHON_LOG_CORRELATION` is **silently ignored unless `OTEL_TRACES_EXPORTER` is also set**, because there are no trace IDs to inject without a tracer. And an explicit `service_name` **takes over** from `OTEL_SERVICE_NAME` rather than merging with it.

### Streaming deployments

The FastAPI instrumentation opens a span for **every ASGI message**, and each
chunk of a streamed response is one message. A deployment that streams a
thousand-token completion therefore produces a thousand `... http send` spans
for that one request, none of which say anything the request span does not.
The cost of building them lands on the event loop, and the cost of encoding
them on the OTLP exporter thread.

Set `OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS=receive,send` to drop them while
keeping the per-request server span:

```sh
OTEL_TRACES_EXPORTER=otlp
OTEL_PYTHON_FASTAPI_EXCLUDE_SPANS=receive,send
```

It is off by default, so existing traces are unchanged unless you opt in.
The name matches the one proposed upstream in
[opentelemetry-python-contrib#3992](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3992);
if the instrumentation grows native support, the same configuration keeps
working. The setting needs a version of
`opentelemetry-instrumentation-fastapi` that accepts `exclude_spans` — on an
older one it is reported as a warning and otherwise ignored.

## What gets instrumented

When tracing is on:

- FastAPI — server spans per request.
- `urllib` from the standard library.
- `requests`, `aiohttp` and `httpx`, each only if that library is installed.
- Python `logging`, which is what adds the trace and span ID fields.

When metrics are on:

- FastAPI — HTTP server metrics.
- The host process — CPU, memory, network and runtime metrics.

FastAPI is instrumented if **either** tracing or metrics is configured. Enabling log export alone does not instrument it.

If you have `add_healthcheck=True`, every `GET /health` produces a span. `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS=health` removes that noise.

## Prometheus

`OTEL_METRICS_EXPORTER=prometheus` starts a second HTTP server, separate from uvicorn, on `OTEL_EXPORTER_PROMETHEUS_PORT`:

```sh
OTEL_METRICS_EXPORTER=prometheus
OTEL_EXPORTER_PROMETHEUS_PORT=9464
```

It listens on all interfaces and does not appear in the FastAPI route table, so it is not covered by anything you mount on the app. Expose or firewall it deliberately.

Both exporters can run at once — `OTEL_METRICS_EXPORTER=otlp,prometheus` pushes to the collector and serves scrapes.

## Missing dependencies

Asking for a signal without the extra installed raises at startup:

```txt
→ ValueError: Missing telemetry dependencies. Install the package with the
  extras: aidial-sdk[telemetry]
```

A `TelemetryConfig` that enables nothing returns before the import is attempted, which is why it stays safe on an installation without the extra.
