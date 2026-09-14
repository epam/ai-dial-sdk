
# Logging

The SDK logs to the console (stderr) through stdlib `logging`, configured from
environment variables. There are **three disjoint ways** to render records —
pick exactly one with the decision tree below, then jump to its section for
defaults and examples.

## Which one do I pick?

```txt
Do you want JSON in a shape you define
(your own keys, nesting, subset of fields)?
│
├─ YES ──────────► DIAL_SDK_LOG_FORMAT=json ───────────────────────────► §1
│                   DIAL_SDK_JSON_LOG_FORMAT=<template>
│                   the only way to get custom-shaped JSON
│
└─ NO ─► Do you need OTel-native structured logs (rich attributes + resource
         + trace context, ready for a log pipeline), shape fixed by OTel?
         │
         ├─ YES ─► OTEL_LOGS_EXPORTER=console  ────────────────────────► §3
         │
         └─ NO ──► Text, then. Whose template?
                   │
                   ├─ OTel's, trace fields already in it ──────────────► §2
                   │   OTEL_TRACES_EXPORTER=otlp
                   │   OTEL_PYTHON_LOG_CORRELATION=true
                   │
                   └─ Yours (the default, no telemetry required) ──────► §1
                       DIAL_SDK_LOG_FORMAT=text (colored, human-readable)
                       DIAL_SDK_TEXT_LOG_FORMAT=<template>
```

Required var in **bold**, optional (customization) vars in plain:

| You want | Set | Section |
| --- | --- | --- |
| **JSON in your own shape** | **`DIAL_SDK_LOG_FORMAT=json`** · `DIAL_SDK_JSON_LOG_FORMAT` · `DIAL_SDK_LOG` | [§1](#1-dial-sdk-formatter) |
| **Text in your own format** (default) | **`DIAL_SDK_LOG_FORMAT=text`** · `DIAL_SDK_TEXT_LOG_FORMAT` · `DIAL_SDK_LOG` | [§1](#1-dial-sdk-formatter) |
| **Text in OTel's correlated format**, no template to write | **`OTEL_TRACES_EXPORTER=otlp`** **and** **`OTEL_PYTHON_LOG_CORRELATION=true`** · `OTEL_PYTHON_LOG_FORMAT` | [§2](#2-otel-log-correlation) |
| **OTel-native structured logs** (shape fixed by OTel) | **`OTEL_LOGS_EXPORTER=console`** or `otlp` | [§3](#3-otel-log-export) |

**Prerequisite:** §2 and §3 require telemetry — the `telemetry` extra
(`aidial-sdk[telemetry]`) **and** `DIALApp(telemetry_config=TelemetryConfig())`.
§2 additionally requires tracing to be enabled (`OTEL_TRACES_EXPORTER=otlp`):
`OTEL_PYTHON_LOG_CORRELATION=true` on its own is a no-op, since there is no
trace context to inject. §1 works with or without telemetry. The three ways are mutually exclusive: enabling §3
makes the SDK ignore §1's format vars; §2 replaces §1's text formatter with
OTel's.

Level is orthogonal to all three — set it with `DIAL_SDK_LOG` (default
`WARNING`).

## 1. DIAL SDK formatter

The default. The SDK renders its own records; you choose text or JSON and
customize the template. No telemetry required.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DIAL_SDK_LOG` | `WARNING` | Level for the `aidial_sdk` logger. |
| `DIAL_SDK_LOG_FORMAT` | `text` | `text` (colored, human-readable) or `json` (one line per record). |
| `DIAL_SDK_TEXT_LOG_FORMAT` | see below | `%`-style format string used when format is `text`. |
| `DIAL_SDK_JSON_LOG_FORMAT` | see below | JSON template used when format is `json`. |

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

### Adding trace and span IDs

Trace/span IDs exist only when tracing is on. Enable it with a `TelemetryConfig`
**and** the OTLP trace exporter:

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

**JSON** auto-adds every `otel*` field present on the record — nothing to amend:

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

**Text** has no auto-add and no missing-field fallback — add the placeholders
yourself, and only when tracing is guaranteed on (otherwise it raises
`KeyError` and drops the line):

```sh
DIAL_SDK_TEXT_LOG_FORMAT='%(levelprefix)s | %(asctime)s | trace_id=%(otelTraceID)s span_id=%(otelSpanID)s | %(message)s'
→
INFO:     | 2026-07-16 13:10:42 | trace_id=36d9c402... span_id=61f3846d... | hello
```

## 2. OTel log correlation

`OTEL_PYTHON_LOG_CORRELATION=true` is OTel's own way to add trace context to
**text** logs, with a built-in format overridable via `OTEL_PYTHON_LOG_FORMAT`.
Requires telemetry **and** tracing — it only takes effect together with
`OTEL_TRACES_EXPORTER=otlp`; without it the SDK builds no `TracingConfig` and
the flag is silently ignored. Its handler takes precedence over §1's text
formatter.

Versus §1 text with `%(otelTraceID)s` placeholders: same information, but the
template is OTel's ready-made one and it renders `0` rather than raising
`KeyError` when tracing is off.

```sh
OTEL_TRACES_EXPORTER=otlp
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

## 3. OTel log export

`OTEL_LOGS_EXPORTER` selects the [OTel](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
log pipeline (comma-separated list). Requires telemetry.

| Value | Effect |
| --- | --- |
| `otlp` | Ships log records to an OTLP collector as structured data (trace context attached automatically). |
| `console` | Emits each record as a single compact JSON object per line on **stderr**, via OTel's console exporter. |

Values combine, e.g. `OTEL_LOGS_EXPORTER=otlp,console`. When the list contains
`console`, records are emitted as structured OTel JSON and the
`DIAL_SDK_LOG_FORMAT`, `DIAL_SDK_JSON_LOG_FORMAT`, and `DIAL_SDK_TEXT_LOG_FORMAT`
variables (§1) are **ignored**.

Each record is written as one line, e.g.:

```json
{"body": "Received chat completion request", "severity_number": 9, "severity_text": "INFO", "attributes": {"deployment": "gpt-4o", "code.file.path": "/app/my_app/application.py", "code.function.name": "chat_completion", "code.line.number": 128}, "dropped_attributes": 0, "timestamp": "2026-07-21T15:21:25.644740Z", "observed_timestamp": "2026-07-21T15:21:25.644895Z", "trace_id": "0x5b8aa5a2d2c872e8321cf37308d69df2", "span_id": "0x051581bf3cb55c13", "trace_flags": 1, "resource": {"attributes": {"telemetry.sdk.language": "python", "telemetry.sdk.name": "opentelemetry", "telemetry.sdk.version": "1.39.1", "service.name": "my-dial-app"}, "schema_url": ""}, "event_name": ""}
```

## Extending the active mode to your own loggers

Whichever way you picked configures **only** the SDK's own loggers
(`aidial_sdk`, `uvicorn`).

To make your application's loggers render the same way — no matter which of the
three is active — call `configure_root_logger()` once at startup, **after**
`DIALApp()`:

```python
import logging

from aidial_sdk import DIALApp, configure_root_logger
from aidial_sdk.telemetry.types import TelemetryConfig

app = DIALApp(telemetry_config=TelemetryConfig())
configure_root_logger()

for name in ("my-app-logger", "third-party-package"):
    logging.getLogger(name).setLevel("INFO")
```

It routes every logger through a single console handler on the **root** logger,
adapting to the active mode:

- **§1** — installs that handler with the SDK format, so all loggers honor
  `DIAL_SDK_LOG_FORMAT` too. It **takes over** the console: any existing stderr
  handler on root is dropped — including those installed by third-party SDKs
  such as Anthropic's and OpenAI's — so their logs render in the SDK format too.
- **§2 / §3** — defers to the handler OTel already installed on root, so your
  loggers flow through the correlation/export pipeline unchanged.

`configure_root_logger()` is idempotent and does **not** change the root
logger's level (stdlib default `WARNING`) — set levels per logger, as above.
