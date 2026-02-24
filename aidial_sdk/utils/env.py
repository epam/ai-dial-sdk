import os


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in ["true", "1"]


def env_var_list(name: str) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return []
    return value.split(",")
