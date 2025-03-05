from typing import TYPE_CHECKING, Any, Dict, Optional, Type, TypeVar, Union

from aidial_sdk.pydantic._compat import PYDANTIC_V2

if TYPE_CHECKING:
    import pydantic as pyd
else:
    if PYDANTIC_V2:
        import pydantic as pyd
    else:
        import pydantic.v1 as pyd


_ModelT = TypeVar("_ModelT", bound=pyd.BaseModel)


def Field(*args, **kwargs) -> Any:
    if PYDANTIC_V2:
        import aidial_sdk.pydantic.v2 as pyd2

        return pyd2.Field(*args, **kwargs)
    else:
        return pyd.Field(*args, **kwargs)


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
    deep: bool = False
) -> _ModelT:
    if PYDANTIC_V2:
        return model.model_copy(update=update, deep=deep)
    return model.copy(  # pyright: ignore[reportDeprecated]
        update=update, deep=deep
    )


def model_dump(
    model: pyd.BaseModel, *, exclude_none: bool = False
) -> Dict[str, Any]:
    if PYDANTIC_V2:
        return model.model_dump(exclude_none=exclude_none)
    return model.dict(  # pyright: ignore[reportDeprecated]
        exclude_none=exclude_none
    )
