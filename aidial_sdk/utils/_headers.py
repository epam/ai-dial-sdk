from typing import List, Mapping


def hide_headers(
    obj: Mapping[str, str], hidden: List[str]
) -> Mapping[str, str]:
    hidden_set = {header.lower() for header in hidden}

    def custom_str():
        display_headers = {
            k: ("**********" if k.lower() in hidden_set else v)
            for k, v in obj.items()
        }
        return str(display_headers)

    obj.__str__ = custom_str
    obj.__repr__ = custom_str

    return obj
