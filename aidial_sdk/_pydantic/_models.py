from __future__ import annotations

from typing import Any, cast

import pydantic
from typing_extensions import Literal, override

from ._compat import PYDANTIC_V2
from ._types import IncEx
from ._utils import json_safe

__all__ = ["BaseModel"]


class BaseModel(pydantic.BaseModel):
    def to_dict(
        self,
        *,
        mode: Literal["json", "python"] = "python",
        use_api_names: bool = True,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        warnings: bool = True,
    ) -> dict[str, object]:
        return self.model_dump(
            mode=mode,
            by_alias=use_api_names,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            warnings=warnings,
        )

    def to_json(
        self,
        *,
        indent: int | None = 2,
        use_api_names: bool = True,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        warnings: bool = True,
    ) -> str:
        return self.model_dump_json(
            indent=indent,
            by_alias=use_api_names,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            warnings=warnings,
        )

    if not PYDANTIC_V2:
        # we define aliases for some of the new pydantic v2 methods so
        # that we can just document these methods without having to specify
        # a specific pydantic version as some users may not know which
        # pydantic version they are currently using

        @override
        def model_dump(
            self,
            *,
            mode: Literal["json", "python"] | str = "python",
            include: IncEx | None = None,
            exclude: IncEx | None = None,
            by_alias: bool = False,
            exclude_unset: bool = False,
            exclude_defaults: bool = False,
            exclude_none: bool = False,
            round_trip: bool = False,
            warnings: bool | Literal["none", "warn", "error"] = True,
            context: dict[str, Any] | None = None,
            serialize_as_any: bool = False,
        ) -> dict[str, Any]:
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
                include=include,  # type: ignore
                exclude=exclude,  # type: ignore
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
            )

            return (
                cast(dict[str, Any], json_safe(dumped))
                if mode == "json"
                else dumped
            )

        @override
        def model_dump_json(
            self,
            *,
            indent: int | None = None,
            include: IncEx | None = None,
            exclude: IncEx | None = None,
            by_alias: bool = False,
            exclude_unset: bool = False,
            exclude_defaults: bool = False,
            exclude_none: bool = False,
            round_trip: bool = False,
            warnings: bool | Literal["none", "warn", "error"] = True,
            context: dict[str, Any] | None = None,
            serialize_as_any: bool = False,
        ) -> str:
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
            return super().json(  # type: ignore[reportDeprecated]
                indent=indent,
                include=include,  # type: ignore
                exclude=exclude,  # type: ignore
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
            )
