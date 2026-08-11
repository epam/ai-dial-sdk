import json
import sys
from os import linesep
from typing import IO

from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk._logs.export import ConsoleLogRecordExporter


class OneLineJsonConsoleLogRecordExporter(ConsoleLogRecordExporter):
    def __init__(self, out: IO = sys.stderr):
        super().__init__(
            out=out,
            formatter=self._format,
        )

    @staticmethod
    def _format(record: ReadableLogRecord) -> str:
        return (
            json.dumps(json.loads(record.to_json()), separators=(",", ":"))
            + linesep
        )
