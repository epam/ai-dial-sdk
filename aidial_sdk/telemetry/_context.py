import contextlib
from collections.abc import Iterator

from opentelemetry.context import Context, attach, detach


@contextlib.contextmanager
def reset_otel_context() -> Iterator[None]:
    token = attach(Context())
    try:
        yield
    finally:
        detach(token)
