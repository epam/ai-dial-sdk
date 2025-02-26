from typing import TYPE_CHECKING, Any, TypeVar, cast

import pydantic
from pydantic.fields import FieldInfo
from typing_extensions import Literal

from ._types import IncEx

_ModelT = TypeVar("_ModelT", bound=pydantic.BaseModel)

# --------------- Pydantic v2 compatibility ---------------

# Pyright incorrectly reports some of our functions as overriding a method when they don't
# pyright: reportIncompatibleMethodOverride=false

PYDANTIC_V2 = pydantic.VERSION.startswith("2.")

# refactored config
if TYPE_CHECKING:
    from pydantic import ConfigDict as ConfigDict
else:
    if PYDANTIC_V2:
        from pydantic import ConfigDict
    else:
        # TODO: provide an error message here?
        ConfigDict = None


# renamed methods / properties
def parse_obj(model: type[_ModelT], value: object) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_validate(value)
    else:
        return cast(
            _ModelT, model.parse_obj(value)
        )  # pyright: ignore[reportDeprecated, reportUnnecessaryCast]


def field_is_required(field: FieldInfo) -> bool:
    if PYDANTIC_V2:
        return field.is_required()
    return field.required  # type: ignore


def field_get_default(field: FieldInfo) -> Any:
    value = field.get_default()
    if PYDANTIC_V2:
        from pydantic_core import PydanticUndefined

        if value == PydanticUndefined:
            return None
        return value
    return value


def field_outer_type(field: FieldInfo) -> Any:
    if PYDANTIC_V2:
        return field.annotation
    return field.outer_type_  # type: ignore


def get_model_config(model: type[pydantic.BaseModel]) -> Any:
    if PYDANTIC_V2:
        return model.model_config
    return model.__config__  # type: ignore


def get_model_fields(model: type[pydantic.BaseModel]) -> dict[str, FieldInfo]:
    if PYDANTIC_V2:
        return model.model_fields
    return model.__fields__  # type: ignore


def model_copy(
    model: _ModelT, *, update: dict[str, Any] | None = None, deep: bool = False
) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_copy(update=update, deep=deep)
    return model.copy(update=update, deep=deep)  # type: ignore


def model_json(model: pydantic.BaseModel, *, indent: int | None = None) -> str:
    if PYDANTIC_V2:
        return model.model_dump_json(indent=indent)
    return model.json(indent=indent)  # type: ignore


def model_dump(
    model: pydantic.BaseModel,
    *,
    exclude_none: bool = False,
    exclude: IncEx | None = None,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    warnings: bool = True,
    mode: Literal["json", "python"] = "python",
) -> dict[str, Any]:
    if PYDANTIC_V2 or hasattr(model, "model_dump"):
        return model.model_dump(
            mode=mode,
            exclude_none=exclude_none,
            exclude=exclude,  # type: ignore
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            # warnings are not supported in Pydantic v1
            warnings=warnings if PYDANTIC_V2 else True,
        )
    return cast(
        "dict[str, Any]",
        model.dict(  # pyright: ignore[reportDeprecated, reportUnnecessaryCast]
            exclude_none=exclude_none,
            exclude=exclude,  # type: ignore
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
        ),
    )


def model_parse(model: type[_ModelT], data: Any) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_validate(data)
    return model.parse_obj(data)  # pyright: ignore[reportDeprecated]


def model_parse_json(model: type[_ModelT], data: str | bytes) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_validate_json(data)
    return model.parse_raw(data)  # pyright: ignore[reportDeprecated]


def model_json_schema(model: type[_ModelT]) -> dict[str, Any]:
    if PYDANTIC_V2:
        return model.model_json_schema()
    return model.schema()  # pyright: ignore[reportDeprecated]
