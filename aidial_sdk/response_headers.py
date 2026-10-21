"""Response headers a DIAL component must not relay downstream.

A component sitting in front of an upstream API - a model adapter proxying the
vendor's response, an interceptor rebuilding it - receives the upstream's
response headers and tends to pass them on. Some of them describe the
**upstream hop**, not the response the component itself emits:

* hop-by-hop headers (RFC 9110 7.6.1). ``transfer-encoding`` is the harmful
  one: the ASGI server computes its own ``content-length`` for the body the
  component emits, and a message carrying both is rejected by a strict HTTP
  parser (RFC 9112 6.2) - DIAL Core being one. A relayed ``connection: close``
  tears down the *downstream* connection once the response is over.
* ``server`` and ``date``, which the ASGI server supplies itself. Both are
  singleton fields (RFC 9110 5.6.6), so the upstream's copy duplicates them.

Which headers these are follows from the HTTP spec alone, never from what the
component does, so ``NonForwardableHeadersMiddleware`` strips them from every
response the app emits and takes no configuration:

* an app built on ``DIALApp`` has it installed already - nothing to do;
* an app built on plain ``FastAPI``/``Starlette`` installs it once::

      app = FastAPI()
      app.add_middleware(NonForwardableHeadersMiddleware)

  It covers the whole app, including sub-apps mounted into it, so a passthrough
  proxy mounted as one needs no strip of its own.

``content-length`` and ``content-encoding`` are a different matter: they are
accurate for the upstream body and go stale only once a component reads and
rebuilds it. The middleware cannot tell a stale one from the correct one the
ASGI server has just computed, so the rebuilding code drops them itself, on the
upstream headers it is about to reuse::

      body = await upstream_response.aread()
      strip_stale_content_headers(upstream_response.headers)
      return Response(content=body, headers=upstream_response.headers)
"""

from collections.abc import MutableMapping

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HOP_BY_HOP_HEADERS = frozenset(
    {
        b"connection",
        b"keep-alive",
        b"proxy-authenticate",
        b"proxy-authorization",
        b"te",
        b"trailer",
        b"transfer-encoding",
        b"upgrade",
    }
)

_SERVER_MANAGED_HEADERS = frozenset({b"server", b"date"})

_NON_FORWARDABLE_HEADERS = _HOP_BY_HOP_HEADERS | _SERVER_MANAGED_HEADERS

_STALE_CONTENT_HEADERS = ("content-length", "content-encoding")


class NonForwardableHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (key, value)
                    for key, value in message["headers"]
                    if key.lower() not in _NON_FORWARDABLE_HEADERS
                ]
            await send(message)

        await self.app(scope, receive, send_wrapper)


def strip_stale_content_headers(headers: MutableMapping[str, str]) -> None:
    """Drop from `headers` the content headers describing the upstream body.

    Call it on the upstream response headers once the body they describe has
    been read and rebuilt, so that the framing and the content coding of the
    new body are recomputed rather than inherited.
    """
    for header in _STALE_CONTENT_HEADERS:
        headers.pop(header, None)
