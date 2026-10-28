import os


def get_env_int(name: str, default: int) -> int:
    return int(os.getenv(name) or default)
