from functools import cache as functools_cache

import httpx

from aidial_sdk.translators.messages_to_chat_completions.utils.cache import (
    cache,
)
from aidial_sdk.translators.messages_to_chat_completions.utils.constants import (
    ANTHROPIC_MAX_CONNECTIONS,
    ANTHROPIC_MAX_KEEPALIVE_CONNECTIONS,
    ANTHROPIC_POOL_TIMEOUT,
    DEFAULT_TIMEOUTS,
)


@functools_cache
def get_default_anthropic_timeout() -> httpx.Timeout:
    # Providing a timeout marginally different from the default Anthropic timeout
    # in order to disable the check that throws an error when
    # stream=False & max_tokens>=128K/6:
    # https://github.com/anthropics/anthropic-sdk-python/blob/f5bdf5137cc3da4d3663aedb8c63d54652981c3b/src/anthropic/resources/beta/messages/messages.py#L2175-L2176

    timeout = DEFAULT_TIMEOUTS.as_dict()
    timeout["connect"] *= 1.0001  # type: ignore
    # Fail fast when the connection pool is exhausted instead of queueing
    # for the whole request timeout.
    timeout["pool"] = ANTHROPIC_POOL_TIMEOUT
    return httpx.Timeout(**timeout)


async def _close_http_client(client: httpx.AsyncClient) -> None:
    await client.aclose()


@cache(close=_close_http_client)
def get_anthropic_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=get_default_anthropic_timeout(),
        follow_redirects=True,
        limits=httpx.Limits(
            # Max number of concurrent requests to the same upstream.
            # It limits number of concurrent requests.
            # `max_connections+1`-th request will be *blocked* until some other request has finished.
            max_connections=ANTHROPIC_MAX_CONNECTIONS,
            # Max number of idle connection to keep in a connection pool.
            max_keepalive_connections=ANTHROPIC_MAX_KEEPALIVE_CONNECTIONS,
        ),
    )
