from typing import Any, Dict, Optional, Type, TypeVar, Union

from aidial_sdk._pydantic import PYDANTIC_V2, BaseModel
from aidial_sdk._pydantic import Field as PydField

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def Field(*args, **kwargs) -> Any:
    if PYDANTIC_V2:
        from aidial_sdk.pydantic.v2 import Field as SDKField

        return SDKField(*args, **kwargs)
    else:
        return PydField(*args, **kwargs)


def model_parse(model: Type[_ModelT], data: Any) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_validate(data)
    return model.parse_obj(data)  # pyright: ignore[reportDeprecated]


def model_parse_json(model: Type[_ModelT], data: Union[str, bytes]) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_validate_json(data)
    return model.parse_raw(data)  # pyright: ignore[reportDeprecated]


def model_json_schema(model: Type[_ModelT]) -> Dict[str, Any]:
    if PYDANTIC_V2:
        return model.model_json_schema()
    return model.schema()  # pyright: ignore[reportDeprecated]


def model_copy(
    model: _ModelT,
    *,
    update: Optional[Dict[str, Any]] = None,
    deep: bool = False,
) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_copy(update=update, deep=deep)
    return model.copy(  # pyright: ignore[reportDeprecated]
        update=update, deep=deep
    )


def model_dump(
    model: BaseModel, *, exclude_none: bool = False
) -> Dict[str, Any]:
    if PYDANTIC_V2:
        return model.model_dump(exclude_none=exclude_none)
    return model.dict(  # pyright: ignore[reportDeprecated]
        exclude_none=exclude_none
    )
