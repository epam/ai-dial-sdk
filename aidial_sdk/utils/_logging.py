import logging
from typing import TYPE_CHECKING, Never, TextIO, assert_never, cast

from aidial_sdk.utils.logging import logger as log


def remove_stream_handlers(logger: logging.Logger, stream: TextIO):
    for h in logger.handlers[:]:
        if isinstance(h, logging.StreamHandler) and h.stream is stream:
            logger.removeHandler(h)


def log_unexpected(msg: Never) -> None:
    err = f"Ignoring unexpected {msg}"
    if TYPE_CHECKING:
        assert_never(cast(Never, err))
    log.error(err)


def log_unsupported(msg: str) -> None:
    log.debug(f"Ignoring unsupported {msg}")
