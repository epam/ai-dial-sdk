import json
from typing import Any, Set


class IdHashable:
    obj: Any

    def __init__(self, obj: Any) -> None:
        self.obj = obj

    def __hash__(self):
        return id(self.obj)

    def __eq__(self, other: object) -> bool:
        return (type(self), hash(self)) == (type(other), hash(other))

    def __repr__(self):
        return json.dumps(self.obj)


def collect_mutable_objects(a: Any) -> Set[IdHashable]:
    ret: set[IdHashable] = set()

    def _register(obj: Any):
        if isinstance(obj, (dict, list)):
            ret.add(IdHashable(obj))

    def _rec(obj: Any):
        _register(obj)
        if isinstance(obj, dict):
            list(map(_rec, obj.values()))
        elif isinstance(obj, (list, tuple)):
            list(map(_rec, obj))

    _rec(a)

    return ret


def collect_shared_mutable_objects(a: Any, b: Any) -> Set[IdHashable]:
    return collect_mutable_objects(a) & collect_mutable_objects(b)
