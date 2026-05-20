"""
This module provides extensions of `ConfigDict` class and `Field`
descriptor with DIAL-specific features.

These extensions should be used instead of the native counterparts to avoid
deprecation warnings and type-checking issues.
"""

from collections.abc import Callable
from typing import Any, Literal

import pydantic as pyd2

from aidial_sdk._pydantic import PYDANTIC_V2


class ConfigDict(pyd2.ConfigDict):
    chat_message_input_disabled: bool


if not PYDANTIC_V2:

    def Field(*args, **kwargs) -> Any:  # type: ignore
        raise ImportError("The Field helper is only supported in Pydantic v2")

else:
    from pydantic.aliases import AliasChoices, AliasPath
    from pydantic.fields import Field as PydanticField
    from pydantic_core import PydanticUndefined

    from aidial_sdk.chat_completion.form import Button

    _Unset: Any = PydanticUndefined

    def Field(
        default: Any = PydanticUndefined,
        *,
        default_factory: Callable[[], Any] | None = _Unset,
        alias: str | None = _Unset,
        alias_priority: int | None = _Unset,
        validation_alias: str | AliasPath | AliasChoices | None = _Unset,
        serialization_alias: str | None = _Unset,
        title: str | None = _Unset,
        description: str | None = _Unset,
        examples: list[Any] | None = _Unset,
        exclude: bool | None = _Unset,
        discriminator: str | None = _Unset,
        json_schema_extra: dict[str, Any]
        | Callable[[dict[str, Any]], None]
        | None = _Unset,
        frozen: bool | None = _Unset,
        validate_default: bool | None = _Unset,
        repr: bool = _Unset,
        init_var: bool | None = _Unset,
        kw_only: bool | None = _Unset,
        pattern: str | None = _Unset,
        strict: bool | None = _Unset,
        gt: float | None = _Unset,
        ge: float | None = _Unset,
        lt: float | None = _Unset,
        le: float | None = _Unset,
        multiple_of: float | None = _Unset,
        allow_inf_nan: bool | None = _Unset,
        max_digits: int | None = _Unset,
        decimal_places: int | None = _Unset,
        min_length: int | None = _Unset,
        max_length: int | None = _Unset,
        union_mode: Literal["smart", "left_to_right"] = _Unset,
        buttons: list[Button] | None = _Unset,
    ) -> Any:
        if buttons is not _Unset and buttons is not None:
            if json_schema_extra is _Unset or json_schema_extra is None:
                json_schema_extra = {}

            if not callable(json_schema_extra):
                new_extra = {**json_schema_extra, "buttons": buttons}
            else:

                def _extra(x: dict[str, Any]) -> None:
                    json_schema_extra({**x, "buttons": buttons})

                new_extra = _extra
        else:
            new_extra = json_schema_extra

        return PydanticField(
            default=default,
            default_factory=default_factory,
            alias=alias,
            alias_priority=alias_priority,
            validation_alias=validation_alias,
            serialization_alias=serialization_alias,
            title=title,
            description=description,
            examples=examples,
            exclude=exclude,
            discriminator=discriminator,
            json_schema_extra=new_extra,
            frozen=frozen,
            validate_default=validate_default,
            repr=repr,
            init_var=init_var,
            kw_only=kw_only,
            pattern=pattern,
            strict=strict,
            gt=gt,
            ge=ge,
            lt=lt,
            le=le,
            multiple_of=multiple_of,
            allow_inf_nan=allow_inf_nan,
            max_digits=max_digits,
            decimal_places=decimal_places,
            min_length=min_length,
            max_length=max_length,
            union_mode=union_mode,
        )
