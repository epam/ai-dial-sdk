from typing import Any, Optional


def has_method_implemented(obj: Any, method_name: str) -> bool:
    """
    Determine if a method is overridden in an object instance or
    if it is inherited from its class.
    """

    base_method = None
    for cls in type(obj).__mro__[1:]:
        base_method = getattr(cls, method_name, None)
        if base_method is not None:
            break

    this_method = getattr(obj, method_name, None)

    if base_method is None or this_method is None:
        return False

    if hasattr(base_method, "__code__") and hasattr(this_method, "__code__"):
        return base_method.__code__ != this_method.__code__

    return base_method != this_method


def get_method_implementation(obj: Any, method_name: str) -> Optional[Any]:
    """
    Get the method implementation of an object instance.
    """

    if has_method_implemented(obj, method_name):
        return getattr(obj, method_name)
    return None
