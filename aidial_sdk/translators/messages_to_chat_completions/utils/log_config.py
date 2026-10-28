import logging
import os

from aidial_sdk import LogConfig, configure_root_logger


def configure_loggers():
    # By default (in prod) we don't want to print debug messages,
    # because they typically contain prompts.
    app_log_level = os.getenv("LOG_LEVEL", "INFO")

    configure_root_logger(
        LogConfig(
            text_format="%(levelprefix)s | %(asctime)s | %(process)d | %(name)s | %(message)s"
        )
    )

    for name in [
        "app",
        "bedrock",
        "aidial_adapter_anthropic",
        "uvicorn",
        "__main__",
    ]:
        logging.getLogger(name).setLevel(app_log_level)


# Loggers in order from high-level to low-level
# High-level logs from the adapter server
app_logger = logging.getLogger("app")

# LLM requests and responses
bedrock_logger = logging.getLogger("bedrock")
