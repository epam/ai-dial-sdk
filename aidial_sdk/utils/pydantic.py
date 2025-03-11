from typing import Any, Iterator, List, Tuple, Union

from pydantic.v1.error_wrappers import ErrorWrapper, ValidationError
from pydantic.v1.errors import ExtraError

from aidial_sdk.pydantic_v1 import BaseModel


class ExtraAllowModel(BaseModel):
    class Config:
        extra = "allow"


Loc = Tuple[Union[int, str], ...]


def _model_iterate_fields(
    obj: Any, loc: Loc
) -> Iterator[Tuple[BaseModel, Loc]]:
    if isinstance(obj, BaseModel):
        yield (obj, loc)
        for field in obj.__fields__:
            value = getattr(obj, field)
            yield from _model_iterate_fields(value, loc + (field,))
    elif isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            yield from _model_iterate_fields(item, loc + (idx,))
    elif isinstance(obj, dict):
        for key, val in obj.items():
            yield from _model_iterate_fields(val, loc + (key,))


def model_validate_extra_fields(root_model: BaseModel) -> None:
    errors: List[ErrorWrapper] = []

    for model, loc in _model_iterate_fields(root_model, ()):
        declared = set(model.__fields__.keys())
        for key in model.__dict__:
            if key not in declared:
                errors.append(ErrorWrapper(ExtraError(), loc=loc + (key,)))

    if errors:
        raise ValidationError(errors, root_model.__class__)
