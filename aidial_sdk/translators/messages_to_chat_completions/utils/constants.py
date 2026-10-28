import httpx

from aidial_sdk.translators.messages_to_chat_completions.utils.env import (
    get_env_int,
)

ANTHROPIC_MAX_CONNECTIONS = get_env_int("ANTHROPIC_MAX_CONNECTIONS", 1000)
ANTHROPIC_MAX_KEEPALIVE_CONNECTIONS = get_env_int(
    "ANTHROPIC_MAX_KEEPALIVE_CONNECTIONS", 100
)
# Seconds a request waits for a free connection once `ANTHROPIC_MAX_CONNECTIONS` is reached
ANTHROPIC_POOL_TIMEOUT = get_env_int("ANTHROPIC_POOL_TIMEOUT", 10)

# Connect timeout for all upstream requests
CONNECT_TIMEOUT = 5
# Read timeout for long-running inference requests that can take minutes
READ_TIMEOUT = get_env_int("REQUEST_TIMEOUT_SECONDS", 10 * 60)


# Same as Anthropic SDK timeouts: anthropic._constants.DEFAULT_TIMEOUT
DEFAULT_TIMEOUTS = httpx.Timeout(timeout=READ_TIMEOUT, connect=CONNECT_TIMEOUT)
