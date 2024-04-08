import os
from typing import List


def env_var_list(name: str) -> List[str]:
    value = os.getenv(name)
    if value is None:
        return []
    return value.split(",")
