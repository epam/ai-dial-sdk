"""
The module provide the basic Pydantic BaseModel extended
with `model_dump` method mimicking the one from Pydantic V2.

All SDK models inherit from this class.

It proves to be useful since
1. `model_dump` method is used extensively in the SDK,
2. the SDK client may call this method on SDK models even if the client uses Pydantic V1.
"""

from datetime import date, datetime
from typing import Any, Dict, Iterable, Mapping, Optional, Set, Union, cast

from typing_extensions import Literal

import aidial_sdk._pydantic as pydantic
from aidial_sdk._pydantic import PYDANTIC_V2

_IncEx = Union[Set[int], Set[str], Dict[int, Any], Dict[str, Any], None]


class BaseModel(pydantic.BaseModel):
    if not PYDANTIC_V2:
        # we define aliases for some of the new pydantic v2 methods so
        # that we can just document these methods without having to specify
        # a specific pydantic version as some users may not know which
        # pydantic version they are currently using

        def model_dump(
            self,
            *,
            mode: Union[Literal["json", "python"], str] = "python",
            include: _IncEx = None,
            exclude: _IncEx = None,
            by_alias: bool = False,
            exclude_unset: bool = False,
            exclude_defaults: bool = False,
            exclude_none: bool = False,
            round_trip: bool = False,
            warnings: Union[bool, Literal["none", "warn", "error"]] = True,
            context: Optional[Dict[str, Any]] = None,
            serialize_as_any: bool = False,
        ) -> Dict[str, Any]:
            if mode not in {"json", "python"}:
                raise ValueError("mode must be either 'json' or 'python'")
            if round_trip is not False:
                raise ValueError("round_trip is only supported in Pydantic v2")
            if warnings is not True:
                raise ValueError("warnings is only supported in Pydantic v2")
            if context is not None:
                raise ValueError("context is only supported in Pydantic v2")
            if serialize_as_any is not False:
                raise ValueError(
                    "serialize_as_any is only supported in Pydantic v2"
                )
            dumped = super().dict(  # pyright: ignore[reportDeprecated]
                include=include,
                exclude=exclude,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
            )

            return (
                cast(Dict[str, Any], _json_safe(dumped))
                if mode == "json"
                else dumped
            )


def _json_safe(data: object) -> object:
    """Translates a mapping / sequence recursively in the same fashion
    as `pydantic` v2's `model_dump(mode="json")`.
    """
    if isinstance(data, Mapping):
        return {
            _json_safe(key): _json_safe(value) for key, value in data.items()
        }

    if isinstance(data, Iterable) and not isinstance(
        data, (str, bytes, bytearray)
    ):
        return [_json_safe(item) for item in data]

    if isinstance(data, (datetime, date)):
        return data.isoformat()

    return data


def model_validator(*, mode: Literal["before", "after"]) -> Any:
    if PYDANTIC_V2:
        return pydantic.model_validator(mode=mode)
    else:
        return pydantic.root_validator(pre=(mode == "before"))  # type: ignore
