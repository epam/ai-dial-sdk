import contextlib
from collections.abc import Iterator

from opentelemetry.context import Context, attach, detach


@contextlib.contextmanager
def reset_trace_context() -> Iterator[None]:
    """Detaches any OpenTelemetry context inherited from another request.

    An ASGI server can start the task serving one request from inside the task
    that served an earlier request on the same connection. ``create_task``
    copies the current ``contextvars``, so the new request begins with the
    earlier request's OpenTelemetry context still attached. Under uvicorn on
    the asyncio event loop this is guaranteed once a request body exceeds 64
    KiB: the body pauses reading, the request's own task resumes it, and
    ``asyncio`` then pins that task's context to the connection's read
    callback (python/cpython#140947, fixed in Python 3.15).

    ``opentelemetry.instrumentation.asgi`` extracts ``traceparent`` only when
    no span is current (``_start_internal_or_server_span``). With one
    inherited, it drops the header without a word and files the request under
    the leftover span as ``INTERNAL`` - putting it in an unrelated trace and
    leaving its real caller's trace with no server span at all.

    Resetting restores the invariant that a server takes its trace context
    from the request, and from nothing else.
    """
    token = attach(Context())
    try:
        yield
    finally:
        detach(token)
