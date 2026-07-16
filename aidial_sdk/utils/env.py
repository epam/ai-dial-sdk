import json
import os


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in ["true", "1"]


def env_float(name: str) -> float | None:
    if (value := os.getenv(name)) is not None:
        return float(value)
    return None


def env_var_list(name: str) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return []
    return value.split(",")


def env_json_dict(name: str, default: dict) -> dict:
    if (value := os.getenv(name)) is not None:
        try:
            obj = json.loads(value)
            if not isinstance(obj, dict):
                raise ValueError("the object isn't a dictionary")
        except Exception as e:
            raise ValueError(
                f"The value of the {name!r} environment variable is expected to be a valid JSON dictionary: {e}."
            )
    return default
