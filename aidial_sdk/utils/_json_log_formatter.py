import json
import logging
from collections import defaultdict


class JsonLogFormatter(logging.Formatter):
    """Render a record through a JSON template whose string leaves are
    `%`-format strings, then `json.dumps` the result (escaping every value).

    Any ``otel*`` field on the record (injected by the OTel logging instrumentor
    when tracing is on) is auto-added to the output, unless the template already
    references it under some key (e.g. ``{"trace_id": "%(otelTraceID)s"}``)."""

    def __init__(self, template: dict, datefmt: str | None = None) -> None:
        super().__init__(datefmt=datefmt)
        self._template = template
        template_str = json.dumps(template)
        self._uses_time = "%(asctime)" in template_str
        self._template_str = template_str

    def _interpolate(self, node: object, fields: dict) -> object:
        if isinstance(node, str):
            return node % fields
        if isinstance(node, dict):
            return {k: self._interpolate(v, fields) for k, v in node.items()}
        if isinstance(node, list):
            return [self._interpolate(v, fields) for v in node]
        return node

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        if self._uses_time:
            record.asctime = self.formatTime(record, self.datefmt)

        # Expose the traceback via %(exc_text)s, escaped like any other value.
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)

        # defaultdict(str): a missing field renders as "" instead of raising.
        rendered = self._interpolate(
            self._template, defaultdict(str, record.__dict__)
        )

        if isinstance(rendered, dict):
            for key, value in record.__dict__.items():
                if (
                    key.startswith("otel")
                    and f"%({key})" not in self._template_str
                ):
                    rendered.setdefault(key, value)

        return json.dumps(rendered, ensure_ascii=False, default=str)
