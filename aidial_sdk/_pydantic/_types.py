from typing import Mapping, TypeVar, Union

import pydantic
from typing_extensions import Set, TypeAlias

ModelT = TypeVar("ModelT", bound=pydantic.BaseModel)

StrBytesIntFloat = Union[str, bytes, int, float]

IncEx: TypeAlias = Union[
    Set[int],
    Set[str],
    Mapping[int, Union["IncEx", bool]],
    Mapping[str, Union["IncEx", bool]],
]
