from typing import TYPE_CHECKING, Any

import pydantic


PYDANTIC_V2 = pydantic.VERSION.startswith("2.")

if TYPE_CHECKING:
    from pydantic import ConfigDict as ConfigDict
else:
    if PYDANTIC_V2:
        from pydantic import ConfigDict
    else:
        ConfigDict = None


def model_dump(
    model: pydantic.BaseModel, *, exclude_none: bool = False
) -> dict[str, Any]:
    if PYDANTIC_V2 or hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=exclude_none)
    return model.dict(  # pyright: ignore[reportDeprecated]
        exclude_none=exclude_none
    )
