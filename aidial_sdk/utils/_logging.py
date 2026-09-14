import logging
from typing import TextIO


def remove_stream_handlers(logger: logging.Logger, stream: TextIO):
    for h in logger.handlers[:]:
        if isinstance(h, logging.StreamHandler) and h.stream is stream:
            logger.removeHandler(h)
