from opentelemetry.context import Context, attach, detach
from starlette.applications import Starlette
from starlette.types import ASGIApp, Receive, Scope, Send


class ResetContextMiddleware:
    """Starts every request from the trace context in its own headers.

    An ASGI server may create the task serving one request from inside the
    task that served the previous request on the same connection - uvicorn
    does so for an already buffered request (``RequestResponseCycle.send``
    -> ``on_response_complete`` -> ``handle_events`` -> ``create_task``).
    ``asyncio.create_task`` copies the current ``contextvars``, so the new
    request starts with the previous request's OpenTelemetry context still
    attached.

    ``opentelemetry.instrumentation.asgi`` extracts ``traceparent`` only
    when no span is current (``_start_internal_or_server_span``). With one
    inherited, it drops the header without a word and files the request
    under the leftover span as ``INTERNAL`` - putting it in an unrelated
    trace and leaving its real caller's trace with no server span at all.

    Detaching what was inherited restores the invariant that a server takes
    its trace context from the request, and from nothing else.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        token = attach(Context())
        try:
            await self.app(scope, receive, send)
        finally:
            detach(token)


def reset_context_per_request(app: Starlette) -> None:
    """Wraps ``app``'s middleware stack in :class:`ResetContextMiddleware`.

    Call it *after* ``FastAPIInstrumentor.instrument_app``, which replaces
    ``build_middleware_stack`` to put its own middleware outermost; the
    reset has to sit outside that one to be of any use.
    """
    build_middleware_stack = app.build_middleware_stack

    def build() -> ASGIApp:
        return ResetContextMiddleware(build_middleware_stack())

    app.build_middleware_stack = build  # type: ignore[method-assign]
