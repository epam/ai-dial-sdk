
# Logging

The SDK logs to the console (stderr) through stdlib `logging`, configured from environment variables.
You pick the **format** (human-readable text or single-line JSON), customize it, and optionally include **trace/span IDs**.

- [Logging](#logging)
  - [Environment variables](#environment-variables)
  - [Log format](#log-format)
  - [Reusing the SDK logger in your app](#reusing-the-sdk-logger-in-your-app)
  - [Trace and span IDs](#trace-and-span-ids)
    - [JSON logs](#json-logs)
    - [Text logs](#text-logs)
      - [OTel log correlation](#otel-log-correlation)
  - [OpenTelemetry log export](#opentelemetry-log-export)
  - [Summary](#summary)

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DIAL_SDK_LOG` | `WARNING` | Level for the `aidial_sdk` logger. |
| `DIAL_SDK_LOG_FORMAT` | `text` | `text` (colored, human-readable) or `json` (one line per record). |
| `DIAL_SDK_TEXT_LOG_FORMAT` | see below | `%`-style format string used when format is `text`. |
| `DIAL_SDK_JSON_LOG_FORMAT` | see below | JSON template used when format is `json`. |

## Log format

`text` (default) renders through uvicorn's `DefaultFormatter`, so
`%(levelprefix)s` gives the colored, aligned level. Default:

```txt
%(levelprefix)s | %(asctime)s | %(name)s | %(process)d | %(message)s
→
INFO:     | 2026-07-16 13:10:41 | aidial_sdk.foo | 13935 | hello
```

`json` renders through a JSON template: a JSON document whose every **string leaf** (at any depth)
is a [`%`-style format string](https://docs.python.org/3/library/logging.html#logrecord-attributes)
interpolated against the record, then `json.dumps`'d (so values are escaped and nesting works). Default:

```txt
{"level": "%(levelname)s", "time": "%(asctime)s", "logger": "%(name)s", "process": "%(process)d", "message": "%(message)s"}
→
{"level": "INFO", "time": "2026-07-16 13:10:41", "logger": "aidial_sdk.foo", "process": "13935", "message": "hello"}
```

Override either with the matching variable:

```sh
DIAL_SDK_TEXT_LOG_FORMAT='%(levelprefix)s %(name)s: %(message)s'
DIAL_SDK_JSON_LOG_FORMAT='{"lvl":"%(levelname)s","msg":"%(message)s","where":{"logger":"%(name)s"}}'
```

## Reusing the SDK logger in your app

Importing `aidial_sdk` (via `DIALApp`) runs `configure_sdk_logger()`, which
formats **only** the SDK's own loggers (`aidial_sdk`, `uvicorn`) — not the root
logger or yours.

To give your loggers the same env-selected format, call `configure_root_logger()` once at startup, **after** `DIALApp()`/telemetry init:

```python
import logging

from aidial_sdk import DIALApp, configure_root_logger
from aidial_sdk.telemetry.types import TelemetryConfig

app = DIALApp(telemetry_config=TelemetryConfig(), ...)
configure_root_logger()

for name in ["app", "bedrock"]:
    logging.getLogger(name).setLevel("INFO")
```

Now every logger emits through one handler honoring `DIAL_SDK_LOG_FORMAT` — run
with `DIAL_SDK_LOG_FORMAT=json` and your `app`/`bedrock` logs become JSON too.

To set any of these in code (overriding the `DIAL_SDK_LOG*` env vars), pass a
`LogConfig` — `configure_root_logger(LogConfig(log_format="json"))`.

`configure_root_logger()` is idempotent and does **not** change the root
logger's level (stdlib default `WARNING`) — set levels per logger, as above.

Avoid raising the *root* level to `DEBUG`: it's the fallback for every logger,
so it would enable the chatty, credential-leaking `DEBUG` streams of `httpx`,
`openai`, etc.

It **takes over** the console: any existing stderr console handler on root is
dropped — including the one `logging.basicConfig()` installs via `ANTHROPIC_LOG`
/ `OPENAI_LOG` — so third-party logs render in the SDK format too.
The one exception is `OTEL_PYTHON_LOG_CORRELATION`, whose handler it
defers to instead.

## Trace and span IDs

Trace/span IDs exist only when tracing is on.
Enable it with a `TelemetryConfig` **and** the OTLP exporter:

```python
app = DIALApp(telemetry_config=TelemetryConfig(), ...)  # requires aidial-sdk[telemetry]
```

```sh
OTEL_TRACES_EXPORTER=otlp
```

This installs OpenTelemetry's logging instrumentor, which injects these fields
onto **every** record (populated while a request span is active):

| Field | Example | No active span |
| --- | --- | --- |
| `%(otelTraceID)s` | `4b45f013470528cf753a7e640da7ca1e` | `0` |
| `%(otelSpanID)s` | `ffcc9d300d9ab692` | `0` |
| `%(otelTraceSampled)s` | `True` | `False` |
| `%(otelServiceName)s` | your `service_name` | *always set* (`unknown_service` if unconfigured) |

### JSON logs

The JSON formatter auto-adds every `otel*` field present on the record, so there's no need to amend the format:

```sh
DIAL_SDK_LOG_FORMAT=json
```

```json
{"level": "INFO", "time": "2026-07-16 13:10:41", "logger": "aidial_sdk", "process": "13935", "message": "hello", "otelTraceID": "4b45f013470528cf753a7e640da7ca1e", "otelSpanID": "ffcc9d300d9ab692", "otelTraceSampled": true, "otelServiceName": "my-service"}
```

Reference a field in your template to rename it *(the auto-added copy is then suppressed)*:

```sh
DIAL_SDK_JSON_LOG_FORMAT='{"level":"%(levelname)s","message":"%(message)s","trace_id":"%(otelTraceID)s"}'
```

```json
{"level": "INFO", "message": "hello", "trace_id": "4b45f013470528cf753a7e640da7ca1e", "otelSpanID": "ffcc9d300d9ab692", "otelTraceSampled": true, "otelServiceName": "my-service"}
```

### Text logs

The text formatter has no auto-add and no missing-field fallback — add the
placeholders yourself, and only when tracing is guaranteed on (otherwise it
raises `KeyError` and drops the line):

```sh
DIAL_SDK_TEXT_LOG_FORMAT='%(levelprefix)s | %(asctime)s | trace_id=%(otelTraceID)s span_id=%(otelSpanID)s | %(message)s'
→
INFO:     | 2026-07-16 13:10:42 | trace_id=36d9c402... span_id=61f3846d... | hello
```

#### OTel log correlation

`OTEL_PYTHON_LOG_CORRELATION=true` is OTel's own way to add trace context to text
logs, with a built-in format overridable via `OTEL_PYTHON_LOG_FORMAT`:

```sh
OTEL_PYTHON_LOG_CORRELATION=true
OTEL_PYTHON_LOG_FORMAT='%(asctime)s %(levelname)s trace_id=%(otelTraceID)s - %(message)s'
→
2026-07-16 13:11:45,585 INFO trace_id=d67e996e... - hello
```

When `OTEL_PYTHON_LOG_FORMAT` isn't set, the [default](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/v0.43b0/instrumentation/opentelemetry-instrumentation-logging/src/opentelemetry/instrumentation/logging/constants.py#L15) is:

```txt
%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s resource.service.name=%(otelServiceName)s trace_sampled=%(otelTraceSampled)s] - %(message)s
→
2026-07-16 13:11:45,585 INFO [aidial_sdk.foo] [app.py:12] [trace_id=d67e996e... span_id=02136a2b... resource.service.name=unknown_service trace_sampled=True] - hello
```

## OpenTelemetry log export

`OTEL_LOGS_EXPORTER` selects the [OTel](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
log pipeline (comma-separated list; requires the `telemetry` extra **and**
telemetry to be enabled — `DIALApp(telemetry_config=TelemetryConfig())`):

| Value | Effect |
| --- | --- |
| `otlp` | Ships log records to an OTLP collector as structured data (trace context attached automatically). |
| `console` | Emits each record as a single compact JSON object per line on **stderr**, via OTel's console exporter. |

When `OTEL_LOGS_EXPORTER` contains `console`, records are emitted as structured
OTel JSON and the `DIAL_SDK_LOG_FORMAT`, `DIAL_SDK_JSON_LOG_FORMAT`, and
`DIAL_SDK_TEXT_LOG_FORMAT` variables are **ignored**. Values combine, e.g.
`OTEL_LOGS_EXPORTER=otlp,console`.

Each record is written as one line, e.g.:

```json
{"body": "Received chat completion request", "severity_number": 9, "severity_text": "INFO", "attributes": {"deployment": "gpt-4o", "code.file.path": "/app/my_app/application.py", "code.function.name": "chat_completion", "code.line.number": 128}, "dropped_attributes": 0, "timestamp": "2026-07-21T15:21:25.644740Z", "observed_timestamp": "2026-07-21T15:21:25.644895Z", "trace_id": "0x5b8aa5a2d2c872e8321cf37308d69df2", "span_id": "0x051581bf3cb55c13", "trace_flags": 1, "resource": {"attributes": {"telemetry.sdk.language": "python", "telemetry.sdk.name": "opentelemetry", "telemetry.sdk.version": "1.39.1", "service.name": "my-dial-app"}, "schema_url": ""}, "event_name": ""}
```

## Summary

| Goal | Set |
| --- | --- |
| OTel JSON format | `OTEL_LOGS_EXPORTER=console` |
| OTel text format with trace context | `OTEL_PYTHON_LOG_CORRELATION=true` |
| Custom JSON format | `DIAL_SDK_LOG_FORMAT=json` + `DIAL_SDK_JSON_LOG_FORMAT` |
| Custom text format | `DIAL_SDK_TEXT_LOG_FORMAT` |
