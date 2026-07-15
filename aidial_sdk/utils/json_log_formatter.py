import json
import logging
from collections import defaultdict


class JsonLogFormatter(logging.Formatter):
    """Render a record through a JSON template whose string leaves are
    `%`-format strings; the whole structure is then `json.dumps`'d, so every
    interpolated value is escaped for free."""

    def __init__(self, template: str, datefmt: str | None = None) -> None:
        super().__init__(datefmt=datefmt)
        self._template = json.loads(template)  # must be valid JSON; fail fast
        self._uses_time = "%(asctime)" in template

    def _interpolate(self, node: object, fields: dict) -> object:
        if isinstance(node, str):
            return node % fields
        if isinstance(node, dict):
            return {k: self._interpolate(v, fields) for k, v in node.items()}
        if isinstance(node, list):
            return [self._interpolate(v, fields) for v in node]
        return node  # numbers, bools, null pass through unchanged

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        if self._uses_time:
            record.asctime = self.formatTime(record, self.datefmt)
        # Expose the traceback via %(exc_text)s; it becomes one escaped string
        # after json.dumps — never appended raw outside the JSON.
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        # defaultdict(str): a missing field renders as "" (e.g. otelTraceID
        # when telemetry is off) instead of raising during %-interpolation.
        rendered = self._interpolate(
            self._template, defaultdict(str, record.__dict__)
        )
        return json.dumps(rendered, ensure_ascii=False, default=str)
