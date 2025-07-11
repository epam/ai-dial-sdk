"""
This module provides extensions of `ConfigDict` class and `Field`
descriptor with DIAL-specific features.

These extensions should be used instead of the native counterparts to avoid
deprecation warnings and type-checking issues.
"""

from typing import Any, Callable, Dict, List, Optional, Union

import pydantic as pyd2
from typing_extensions import Literal

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
        default_factory: Optional[Callable[[], Any]] = _Unset,
        alias: Optional[str] = _Unset,
        alias_priority: Optional[int] = _Unset,
        validation_alias: Optional[
            Union[str, AliasPath, AliasChoices]
        ] = _Unset,
        serialization_alias: Optional[str] = _Unset,
        title: Optional[str] = _Unset,
        description: Optional[str] = _Unset,
        examples: Optional[List[Any]] = _Unset,
        exclude: Optional[bool] = _Unset,
        discriminator: Optional[str] = _Unset,
        json_schema_extra: Optional[
            (Union[Dict[str, Any], Callable[[Dict[str, Any]], None]])
        ] = _Unset,
        frozen: Optional[bool] = _Unset,
        validate_default: Optional[bool] = _Unset,
        repr: bool = _Unset,
        init_var: Optional[bool] = _Unset,
        kw_only: Optional[bool] = _Unset,
        pattern: Optional[str] = _Unset,
        strict: Optional[bool] = _Unset,
        gt: Optional[float] = _Unset,
        ge: Optional[float] = _Unset,
        lt: Optional[float] = _Unset,
        le: Optional[float] = _Unset,
        multiple_of: Optional[float] = _Unset,
        allow_inf_nan: Optional[bool] = _Unset,
        max_digits: Optional[int] = _Unset,
        decimal_places: Optional[int] = _Unset,
        min_length: Optional[int] = _Unset,
        max_length: Optional[int] = _Unset,
        union_mode: Literal["smart", "left_to_right"] = _Unset,
        buttons: Optional[List[Button]] = _Unset,
    ) -> Any:

        if buttons is not _Unset and buttons is not None:
            if json_schema_extra is _Unset or json_schema_extra is None:
                json_schema_extra = {}

            if not callable(json_schema_extra):
                new_extra = {**json_schema_extra, "buttons": buttons}
            else:

                def _extra(x: Dict[str, Any]) -> None:
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
