
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
      - [Legacy alternative](#legacy-alternative)
  - [Summary](#summary)
  - [OTLP log export](#otlp-log-export)

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

If root already has a stderr console handler it didn't install
(e.g. OTEL's via `OTEL_PYTHON_LOG_CORRELATION`), it defers to that and adds
nothing — so the SDK format won't apply to the console.

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

#### Legacy alternative

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

> [!WARNING]
> Prefer `DIAL_SDK_TEXT_LOG_FORMAT`. `OTEL_PYTHON_LOG_CORRELATION` logs every SDK
> record twice (unless `configure_root_logger()` is called) and is text-only
> (ignores `DIAL_SDK_LOG_FORMAT=json`).

## Summary

| Goal | Set |
| --- | --- |
| JSON console | `DIAL_SDK_LOG_FORMAT=json` |
| Customize JSON / text | `DIAL_SDK_JSON_LOG_FORMAT` / `DIAL_SDK_TEXT_LOG_FORMAT` |
| Trace/span in JSON | enable tracing |
| Trace/span in text | enable tracing + add `otel*` placeholders to `DIAL_SDK_TEXT_LOG_FORMAT` |

## OTLP log export

`OTEL_LOGS_EXPORTER=otlp` ships log records to an OTLP collector as structured
data (trace context attached automatically). That pipeline uses no format
string, so the `*_LOG_FORMAT` variables don't affect it — they only control
console output.
