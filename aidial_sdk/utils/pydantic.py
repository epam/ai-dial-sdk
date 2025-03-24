from enum import Enum
from typing import Any, Iterator, List, Tuple, Union

from pydantic.v1.error_wrappers import ErrorWrapper, ValidationError
from pydantic.v1.errors import ExtraError

from aidial_sdk._pydantic import PYDANTIC_V2, ConfigDict
from aidial_sdk._pydantic._compat import BaseModel


class ExtraAllowModel(BaseModel):
    if PYDANTIC_V2:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


_Loc = Tuple[Union[int, str], ...]


# FIXME: make it work for Pydantic v2
def _model_iterate_fields(
    obj: Any, any_types: bool, loc: _Loc
) -> Iterator[Tuple[BaseModel, _Loc]]:
    if isinstance(obj, BaseModel):
        yield (obj, loc)
        any_types = getattr(obj.Config, "arbitrary_types_allowed", False)
        for field in obj.__fields__:
            value = getattr(obj, field)
            yield from _model_iterate_fields(value, any_types, loc + (field,))

    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            yield from _model_iterate_fields(item, any_types, loc + (idx,))

    elif isinstance(obj, dict):
        for key, val in obj.items():
            yield from _model_iterate_fields(val, any_types, loc + (key,))

    elif isinstance(obj, (str, int, float, bool, type(None), Enum)):
        pass

    else:
        err_message = f"Cannot iterate model fields within an object with the unexpected type: {type(obj)}, loc: {loc}"
        assert any_types, err_message


def model_validate_extra_fields(root_model: BaseModel) -> None:
    errors: List[ErrorWrapper] = []

    for model, loc in _model_iterate_fields(root_model, False, ()):
        declared = set(model.__fields__.keys())
        for key in model.__dict__:
            if key not in declared:
                errors.append(ErrorWrapper(ExtraError(), loc=loc + (key,)))

    if errors:
        raise ValidationError(errors, root_model.__class__)
