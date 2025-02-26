import pydantic
from aidial_sdk._pydantic._compat import PYDANTIC_V2
from typing import Any, Type, TypeVar

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
    model: _ModelT, *, update: dict[str, Any] | None = None, deep: bool = False
) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_copy(update=update, deep=deep)
    return model.copy(  # pyright: ignore[reportDeprecated]
        update=update, deep=deep
    )
