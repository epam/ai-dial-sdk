
# Logging

The SDK logs to the console (stderr) through stdlib `logging`, configured from
environment variables. You can pick the **format** (human-readable text or
single-line JSON), customize it, and include **trace/span IDs** for correlation.

- [Logging](#logging)
  - [Environment variables](#environment-variables)
  - [Log format](#log-format)
    - [JSON](#json)
    - [Plain text](#plain-text)
  - [Reusing the SDK logger in your app](#reusing-the-sdk-logger-in-your-app)
  - [Trace and span IDs](#trace-and-span-ids)
    - [Enable tracing](#enable-tracing)
    - [Tracing in JSON logs](#tracing-in-json-logs)
    - [Tracing in text logs](#tracing-in-text-logs)
  - [Summary](#summary)
  - [OTLP log export](#otlp-log-export)

## Environment variables

All variables below are read once at import time — set them before the process starts.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DIAL_SDK_LOG` | `WARNING` | Log level for the `aidial_sdk` logger. |
| `DIAL_SDK_LOG_FORMAT` | `text` | `text` (human-readable, colored) or `json` (one line per record). |
| `DIAL_SDK_TEXT_LOG_FORMAT` | see below | `%`-style format string used when format is `text`. |
| `DIAL_SDK_JSON_LOG_FORMAT` | see below | JSON template used when format is `json`. |

---

## Log format

Set the format to `json`:

```sh
DIAL_SDK_LOG=INFO
DIAL_SDK_LOG_FORMAT=json
```

Console:

```json
{"level": "INFO", "time": "2026-07-16 13:10:41", "logger": "aidial_sdk.foo", "process": "13935", "message": "hello"}
```

Compare with the default `text` format:

```txt
INFO:     | 2026-07-16 13:10:41 | aidial_sdk.foo | 13935 | hello
```

### JSON

The value is **a JSON document**. Every **string leaf** (at any nesting depth) is
treated as a [`%`-style format string](https://docs.python.org/3/library/logging.html#logrecord-attributes)
and interpolated against the log record; the whole structure is then `json.dumps`'d.

```sh
DIAL_SDK_LOG_FORMAT=json
DIAL_SDK_JSON_LOG_FORMAT='{"lvl":"%(levelname)s","msg":"%(message)s","where":{"logger":"%(name)s","pid":"%(process)d"}}'
```

Console:

```json
{"lvl": "INFO", "msg": "hello", "where": {"logger": "aidial_sdk.foo", "pid": "13935"}}
```

Default template:

```json
{"level": "%(levelname)s", "time": "%(asctime)s", "logger": "%(name)s", "process": "%(process)d", "message": "%(message)s"}
```

### Plain text

A plain `%`-style format string (rendered by uvicorn's `DefaultFormatter`, so
`%(levelprefix)s` gives the colored, aligned level).

```sh
DIAL_SDK_TEXT_LOG_FORMAT='%(levelprefix)s %(name)s: %(message)s'
```

Default:

```txt
%(levelprefix)s | %(asctime)s | %(name)s | %(process)d | %(message)s
```

---

## Reusing the SDK logger in your app

Importing `aidial_sdk` (via `DIALApp`) runs `configure_sdk_logger()` once. By
default it configures **only the SDK's own loggers**: it attaches a single stderr
handler using the env-selected format (`DIAL_SDK_LOG_FORMAT`) to the `aidial_sdk`
and `uvicorn` loggers, sets `aidial_sdk` to `DIAL_SDK_LOG` (default `WARNING`),
and stops `uvicorn` from propagating to the root logger. It does **not** touch the
root logger or your application's loggers.

So to give **your** application's loggers the same formatting — instead of
hand-rolling a formatter and a root handler — call `configure_root_logger()` once
at startup:

```python
import logging
import os

from aidial_sdk import DIALApp, configure_root_logger
from aidial_sdk.telemetry.types import TelemetryConfig

app = DIALApp(telemetry_config=TelemetryConfig(), ...)

# Install one root handler using the SDK's env-selected format. Call AFTER
# DIALApp()/telemetry init.
configure_root_logger()

# You only declare your own loggers' levels:
for name in ["app", "bedrock"]:
    logging.getLogger(name).setLevel(os.getenv("LOG_LEVEL", "INFO"))
```

Now every logger — the SDK's, uvicorn's, and yours — is emitted through a single
handler that honors `DIAL_SDK_LOG_FORMAT`. Run with `DIAL_SDK_LOG_FORMAT=json`
and your `app`/`bedrock` logs become JSON too, with no code change:

```json
{"level": "INFO", "time": "2026-07-16 13:10:41", "logger": "app", "process": "13935", "message": "hello from the adapter"}
```

**What it does:** points the SDK/uvicorn loggers at the root logger and installs
**one** console handler there with the SDK's formatter. It's idempotent (a repeat
call replaces that handler rather than stacking a duplicate) and **preserves any
other root handler** — notably the OTLP export handler telemetry adds — so it's
safe to call after `DIALApp()`.

### The `level` argument

`configure_root_logger(level="INFO")` sets the level of the **root** logger — it
does **not** force every logger to `INFO`. Root's level is only the *fallback*
for loggers that don't set their own:

- A logger **without** an explicit level (e.g. a fresh `app` logger, or a
  third-party library) inherits root's level → fires at `INFO`.
- A logger **with** its own level keeps it. `aidial_sdk` stays at `DIAL_SDK_LOG`
  (default `WARNING`); a logger you set to `DEBUG` stays `DEBUG` — regardless of
  the root level.

When `level` is omitted (`None`), the root level is left untouched (stdlib
default `WARNING`), and each logger's own level applies. This is why the example
above sets `app`/`bedrock` levels explicitly rather than relying on the root
level. Note that a logger's own level gates whether a record is *created*; once
created it always reaches the root handler, so a low root level never suppresses
an `INFO` record coming from an `INFO`-level `app` logger.

---

## Trace and span IDs

### Enable tracing

Trace/span IDs only exist when tracing is on. Enable it by passing a
`TelemetryConfig` to your app **and** selecting the OTLP exporter:

```python
from aidial_sdk import DIALApp
from aidial_sdk.telemetry.types import TelemetryConfig

app = DIALApp(telemetry_config=TelemetryConfig(), ...)  # requires aidial-sdk[telemetry]
```

```sh
OTEL_TRACES_EXPORTER=otlp
```

This installs OpenTelemetry's logging instrumentor, which injects these fields
onto **every** log record (populated while a request span is active):

| Field | Example | Value with no active span |
| --- | --- | --- |
| `%(otelTraceID)s` | `4b45f013470528cf753a7e640da7ca1e` | `0` |
| `%(otelSpanID)s` | `ffcc9d300d9ab692` | `0` |
| `%(otelTraceSampled)s` | `True` | `False` |
| `%(otelServiceName)s` | your `service_name` | always set (`unknown_service` if unconfigured) |

### Tracing in JSON logs

Add the `otel*` placeholders to your template. They are populated automatically
under an active span; **you never need to guard against them being absent** — a
missing field renders as `""` (so the same template is safe with tracing off).

```sh
DIAL_SDK_LOG_FORMAT=json
DIAL_SDK_JSON_LOG_FORMAT='{"lvl":"%(levelname)s","msg":"%(message)s","trace_id":"%(otelTraceID)s","span_id":"%(otelSpanID)s"}'
```

Console (inside a request span):

```json
{"lvl": "INFO", "msg": "hello", "trace_id": "4b45f013470528cf753a7e640da7ca1e", "span_id": "ffcc9d300d9ab692"}
```

Without tracing the same setup emits `"trace_id": "", "span_id": ""` — no error.

### Tracing in text logs

**Option A — via `DIAL_SDK_TEXT_LOG_FORMAT`** (recommended for text): add the
placeholders yourself.

```sh
OTEL_TRACES_EXPORTER=otlp
DIAL_SDK_TEXT_LOG_FORMAT='%(levelprefix)s | %(asctime)s | trace_id=%(otelTraceID)s span_id=%(otelSpanID)s | %(message)s'
```

Console:

```txt
INFO:     | 2026-07-16 13:10:42 | trace_id=36d9c402fc8b07cd7644bbf2adbbcec8 span_id=61f3846d5d19881b | hello
```

> ⚠️ Unlike JSON, the text formatter has **no missing-field fallback**. If the
> `otel*` fields aren't on the record (i.e. tracing is *not* enabled) it raises a
> `KeyError` and the log line is dropped. Only put `otel*` fields in the text
> format when tracing is guaranteed on.

**Option B — via `OTEL_PYTHON_LOG_CORRELATION`** — ⚠️ **not recommended.** When
tracing is enabled, setting this makes the OTel instrumentor install its own
root-logger format that already includes trace context, without touching any
`DIAL_SDK_*` variable:

```sh
OTEL_TRACES_EXPORTER=otlp
OTEL_PYTHON_LOG_CORRELATION=true
```

Console:

```txt
2026-07-16 13:11:45,585 INFO [aidial_sdk.foo] [app.py:12] [trace_id=d67e996e... span_id=02136a2b... resource.service.name=unknown_service trace_sampled=True] - hello
```

Override that format with `OTEL_PYTHON_LOG_FORMAT` (default below):

```txt
%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s resource.service.name=%(otelServiceName)s trace_sampled=%(otelTraceSampled)s] - %(message)s
```

> ⚠️ **Why it's not recommended:** it works by adding a handler to the **root**
> logger. Because the SDK already logs through its own handler — and your
> application most likely configures logging itself too — that root handler emits
> a **duplicate** line for every record (double logging). It also can't produce
> JSON (`OTEL_PYTHON_LOG_FORMAT` has no escaping) and breaks
> `DIAL_SDK_LOG_FORMAT=json` (you'd get one JSON line plus one text line per
> record). Use Option A instead.

---

## Summary

| Goal | What to set |
| --- | --- |
| JSON console | `DIAL_SDK_LOG_FORMAT=json` |
| Customize JSON | `DIAL_SDK_JSON_LOG_FORMAT='{…}'` |
| Customize text | `DIAL_SDK_TEXT_LOG_FORMAT='…'` |
| Trace/span in JSON | enable tracing + add `%(otelTraceID)s`/`%(otelSpanID)s` to the JSON template (safe when off) |
| Trace/span in text | enable tracing + add them to `DIAL_SDK_TEXT_LOG_FORMAT` (Option A, recommended). `OTEL_PYTHON_LOG_CORRELATION=true` (Option B) also works but double-logs — avoid. |

**Key difference:** in JSON the `otel*` fields are auto-injected and safe to
reference whether or not tracing is on; in text you must add them manually and
they require tracing to be enabled.

---

## OTLP log export

`OTEL_LOGS_EXPORTER=otlp` ships log records to an OTLP collector as structured
data (trace context attached automatically). That pipeline uses no format string,
so none of the `*_LOG_FORMAT` variables above apply to it — they only affect what
is printed to the console.
