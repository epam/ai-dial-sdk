import os
from typing import List, Optional


def env_var_list(name: str, default: Optional[List[str]] = None) -> List[str]:
    value = os.getenv(name)
    if value is None:
        return default or []
    return value.split(",")
