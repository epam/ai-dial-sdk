def remove_nones(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}
