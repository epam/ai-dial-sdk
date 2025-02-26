from typing import Any, Dict, Type, TypeVar

import pydantic

from aidial_sdk._pydantic import PYDANTIC_V2

_ModelT = TypeVar("_ModelT", bound=pydantic.BaseModel)


def model_parse(model: Type[_ModelT], data: Any) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_validate(data)
    return model.parse_obj(data)  # pyright: ignore[reportDeprecated]


def model_parse_json(model: Type[_ModelT], data: str | bytes) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_validate_json(data)
    return model.parse_raw(data)  # pyright: ignore[reportDeprecated]


def model_copy(
    model: _ModelT, *, update: Dict[str, Any] | None = None, deep: bool = False
) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_copy(update=update, deep=deep)
    return model.copy(  # pyright: ignore[reportDeprecated]
        update=update, deep=deep
    )


def model_dump(
    model: pydantic.BaseModel, *, exclude_none: bool = False
) -> Dict[str, Any]:
    if PYDANTIC_V2 or hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=exclude_none)
    return model.dict(  # pyright: ignore[reportDeprecated]
        exclude_none=exclude_none
    )
