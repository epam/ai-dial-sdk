# OpenTelemetry

- [OpenTelemetry](#opentelemetry)
  - [Which one do I pick?](#which-one-do-i-pick)
  - [1. `TelemetryConfig`](#1-telemetryconfig)
  - [2. Environment variables](#2-environment-variables)
  - [3. `OTEL_CONFIG_FILE`](#3-otel_config_file)
  - [Instrumentation installed by default](#instrumentation-installed-by-default)
  - [The console log exporter](#the-console-log-exporter)
  - [Typical configuration](#typical-configuration)
    - [Via environment variables](#via-environment-variables)
    - [Via `OTEL_CONFIG_FILE`](#via-otel_config_file)
  - [Advanced: custom metric views](#advanced-custom-metric-views)

The SDK ships a ready-made OpenTelemetry setup: traces, metrics and log export
for your FastAPI app and the HTTP clients it uses. There are **three ways to
configure it** — in code, from environment variables, or from a declarative
file.

Install the extra first:

```sh
pip install aidial-sdk[telemetry]
```

Telemetry is always **opt-in** — nothing is configured unless you pass a
`TelemetryConfig`:

```python
from aidial_sdk import DIALApp
from aidial_sdk.telemetry.types import TelemetryConfig

app = DIALApp(telemetry_config=TelemetryConfig())
```

## Which one do I pick?

| You want | Use | Section |
| --- | --- | --- |
| Signals chosen in code, one flag per signal | **`TelemetryConfig(...)`** | [§1](#1-telemetryconfig) |
| The same, chosen at deployment time, no code | **`OTEL_*` variables** | [§2](#2-environment-variables) |
| Anything the OTel schema can express — several exporters per signal, sampling, metric views, limits | **`OTEL_CONFIG_FILE`** | [§3](#3-otel_config_file) |

They compose in one direction only:

```txt
OTEL_CONFIG_FILE   ─── set? ──► the file is the sole source; §1 and §2 ignored
      │
      not set
      │
      ▼
TelemetryConfig(...) ─── field passed explicitly? ──► that value wins
      │
      omitted
      │
      ▼
OTEL_* variables ────────────────────────────────► the default of every field
```

So §2 is not a separate mechanism: the `OTEL_*` variables are simply where
`TelemetryConfig`'s fields get their defaults. §3 replaces both.

Log **formatting** (as opposed to log export) is a separate matter — see
[docs/logging.md](logging.md).

## 1. `TelemetryConfig`

One optional sub-config per signal; `None` (the default) means the signal is
off.

| Field | Type | Purpose |
| --- | --- | --- |
| `service_name` | `str \| None` | `service.name` resource attribute. Falls back to `OTEL_SERVICE_NAME`. |
| `tracing` | `TracingConfig \| None` | Traces. |
| `logs` | `LogsConfig \| None` | Log export. |
| `metrics` | `MetricsConfig \| None` | Metrics. |

| Sub-config | Field | Default | Effect |
| --- | --- | --- | --- |
| `TracingConfig` | `otlp_export` | `"otlp" in OTEL_TRACES_EXPORTER` | Batch-exports spans over OTLP/gRPC. |
| | `logging` | `OTEL_PYTHON_LOG_CORRELATION` | Renders logs in OTel's correlated text format ([§2 of logging.md](logging.md#2-otel-log-correlation)). |
| `LogsConfig` | `otlp_export` | `"otlp" in OTEL_LOGS_EXPORTER` | Batch-exports log records over OTLP/gRPC. |
| | `console_export` | `"console" in OTEL_LOGS_EXPORTER` | Writes log records to the console ([see below](#the-console-log-exporter)). |
| `MetricsConfig` | `otlp_export` | `"otlp" in OTEL_METRICS_EXPORTER` | Periodically pushes metrics over OTLP/gRPC. |
| | `prometheus_export` | `"prometheus" in OTEL_METRICS_EXPORTER` | Serves `/metrics` for scraping. |
| | `port` | `OTEL_EXPORTER_PROMETHEUS_PORT` (`9464`) | Port of that endpoint, bound on `0.0.0.0`. |

```python
from aidial_sdk import DIALApp
from aidial_sdk.telemetry.types import (
    MetricsConfig,
    TelemetryConfig,
    TracingConfig,
)

app = DIALApp(
    telemetry_config=TelemetryConfig(
        service_name="my-dial-app",
        tracing=TracingConfig(otlp_export=True),
        metrics=MetricsConfig(prometheus_export=True, port=9464),
        # logs stay off
    )
)
```

> [!NOTE]
> `TracingConfig()` with no arguments still reads the
> environment for its own fields, but `TelemetryConfig(tracing=TracingConfig())`
> turns tracing **on** regardless of `OTEL_TRACES_EXPORTER`.

## 2. Environment variables

`TelemetryConfig()` with nothing passed configures each signal from the `OTEL_*`
environment — the usual way to run a DIAL application.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OTEL_TRACES_EXPORTER` | | `otlp` enables tracing. |
| `OTEL_LOGS_EXPORTER` | | Comma-separated: `otlp`, `console`. |
| `OTEL_METRICS_EXPORTER` | | Comma-separated: `otlp`, `prometheus`. |
| `OTEL_SERVICE_NAME` | `unknown_service` | `service.name` resource attribute. |
| `OTEL_RESOURCE_ATTRIBUTES` | | Extra resource attributes, `key=value,...`. |
| `OTEL_EXPORTER_PROMETHEUS_PORT` | `9464` | Port of the Prometheus endpoint. |
| `OTEL_PYTHON_LOG_CORRELATION` | `false` | Log correlation; needs tracing on. |
| `OTEL_PROPAGATORS` | `tracecontext,baggage` | Context propagators. |

An unset variable leaves its signal off — no variables at all means an empty
`TelemetryConfig()` configures nothing.

## 3. `OTEL_CONFIG_FILE`

When `OTEL_CONFIG_FILE` points at a YAML or JSON file in the
[declarative configuration](https://opentelemetry.io/docs/specs/otel/configuration/)
format, **that file is the sole source** of the OpenTelemetry setup:
`TelemetryConfig` fields and the `OTEL_*` variables of §2 are ignored. An empty
`TelemetryConfig()` is all the opt-in the file needs.

Use it for anything the two flags per signal cannot say: several exporters for
one signal, samplers, span/attribute limits, metric views, per-processor
batching.

The file is read at `DIALApp()` time, so a `load_dotenv()` that runs after the
imports still counts.

What the SDK adds on top of the file:

- the [default instrumentation](#instrumentation-installed-by-default), the same
  as for §1/§2;
- `tracecontext,baggage` propagators, unless the file sets `propagator` — the
  schema's own default is *no* propagation, which would drop incoming trace
  context;
- the FastAPI instrumentation, which the file cannot reach (the app exists
  before the file is read);
- a stdlib `logging` bridge, when the file configures a `logger_provider`;
- the [one-line console exporter](#the-console-log-exporter) in place of the
  stock `console` one.

Two gotchas:

- **Batching env vars do not reach the file.** For `logger_provider` processors
  and metric readers the schema's defaults (log batching every 1000 ms, metric
  export every 60000 ms) win over `OTEL_BLRP_*` and
  `OTEL_METRIC_EXPORT_INTERVAL`. Spell the values out in the file instead.
  Exporter-level variables such as `OTEL_EXPORTER_OTLP_ENDPOINT` still apply,
  and span batching (`OTEL_BSP_*`) still works.
- **Log correlation must be asked for.** §1/§2 enable the `logging`
  instrumentor together with tracing; a file has to list it (see the example
  below), otherwise records carry no `otel*` fields.

## Instrumentation installed by default

Whichever way you configure it, the SDK enables these:

| Instrumentation | When | Effect |
| --- | --- | --- |
| FastAPI | traces or metrics on | Server span per request (traces), plus `http.server.duration`, `http.server.active_requests` and `http.server.response_size` (metrics). |
| `requests`, `aiohttp-client`, `urllib`, `httpx` | traces on, package importable | Client span per outgoing request, and `traceparent` injected into its headers — this is what continues your trace into DIAL Core and upstream models. |
| `system_metrics` | metrics on | Process and runtime metrics: CPU, memory, file descriptors, context switches, GC. |
| `logging` | traces on, **§1/§2 only** | Adds `otelTraceID`, `otelSpanID`, `otelTraceSampled`, `otelServiceName` to every log record ([§1 of logging.md](logging.md#adding-trace-and-span-ids)). |

All four HTTP clients ship with the `telemetry` extra, so all four are
instrumented in practice. They cost nothing when the client is unused, but they
do mean **every** outgoing request gets a span — filter by
`http.url`/`http.target` in your backend rather than in the SDK.

A file may add more under `instrumentation/development.python`, and switch one
off with `enabled: false`:

```yaml
instrumentation/development:
  python:
    httpx:
      enabled: false
```

## The console log exporter

`logs=console` (or a `console` exporter in the file) emits **one compact JSON
object per line on stderr**, rather than the multi-line indented JSON on stdout
of OTel's stock console exporter:

```json
{"body":"Received chat completion request","severity_text":"INFO","attributes":{"deployment":"gpt-4o"},"timestamp":"2026-07-21T15:21:25.644740Z","trace_id":"0x5b8aa5a2d2c872e8321cf37308d69df2","span_id":"0x051581bf3cb55c13","resource":{"attributes":{"service.name":"my-dial-app"}}}
```

One line per record is what log collectors expect, and stderr is where the rest
of the application's logs already go. The exporter also **takes over the
console**: the SDK's own text handler steps aside, so records are not rendered
twice. See [§3 of logging.md](logging.md#3-otel-log-export).

## Typical configuration

Tracing and logs to an OTLP collector, logs also to the console, metrics
scraped by Prometheus.

### Via environment variables

```sh
OTEL_SERVICE_NAME=my-dial-app
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317
OTEL_TRACES_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp,console
OTEL_METRICS_EXPORTER=prometheus
```

```python
app = DIALApp(telemetry_config=TelemetryConfig())
```

### Via `OTEL_CONFIG_FILE`

The same setup, spelled out. Note the explicit `logging` instrumentor, which
§1/§2 add on their own:

```yaml
# otel.yaml — OTEL_CONFIG_FILE=otel.yaml
file_format: "1.0-rc.1"
resource:
  attributes:
    - name: service.name
      value: my-dial-app
tracer_provider:
  processors:
    - batch:
        exporter:
          otlp_grpc:
            endpoint: http://collector:4317
logger_provider:
  processors:
    - batch:
        exporter:
          otlp_grpc:
            endpoint: http://collector:4317
    - simple:
        exporter:
          console: {}
meter_provider:
  readers:
    - pull:
        exporter:
          prometheus/development:
            host: "0.0.0.0"
            port: 9464
instrumentation/development:
  python:
    logging:
      inject_trace_context: true
```

```python
app = DIALApp(telemetry_config=TelemetryConfig())
```

## Advanced: custom metric views

Neither `TelemetryConfig` nor the `OTEL_*` variables can change how an
instrument is aggregated. A file can, through `meter_provider.views`.

`http.server.duration` is recorded in **milliseconds**, and its default buckets
stop at 10 s — every slower request lands in `+Inf`, which is useless for an LLM
application where a request routinely takes a minute. Extend the boundaries up
to 5 minutes:

```yaml
# otel.yaml — OTEL_CONFIG_FILE=otel.yaml
file_format: "1.0-rc.1"
resource:
  attributes:
    - name: service.name
      value: my-dial-app
meter_provider:
  readers:
    - pull:
        exporter:
          prometheus/development:
            host: "0.0.0.0"
            port: 9464
  views:
    - selector:
        instrument_name: http.server.duration
      stream:
        aggregation:
          explicit_bucket_histogram:
            boundaries:
              # the SDK default boundaries stop at 10s...
              [0, 5, 10, 25, 50, 75, 100, 250, 500, 750,
               1000, 2500, 5000, 7500, 10000,
               # ...these are the extra ones
               15000, 20000, 30000, 60000, 120000, 300000]
```

`:9464/metrics` then reports the added buckets, and every other instrument keeps
its defaults:

```txt
http_server_duration_milliseconds_bucket{...,le="60000"} 3.0
http_server_duration_milliseconds_bucket{...,le="300000"} 3.0
```
