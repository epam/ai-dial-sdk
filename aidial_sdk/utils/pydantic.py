from enum import Enum
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, Union

from aidial_sdk._pydantic import PYDANTIC_V2, ConfigDict, FieldInfo
from aidial_sdk._pydantic._compat import BaseModel, model_validator


class ExtraAllowModel(BaseModel):
    if PYDANTIC_V2:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


class IgnoreIndex(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def strip_index(cls, data: Any) -> Any:
        if (
            isinstance(data, Mapping)
            and (idx := data.get("index")) is not None
            and isinstance(idx, int)
        ):
            d = dict(data)
            d.pop("index")
            return d
        return data


_Loc = Tuple[Union[int, str], ...]


def _get_model_fields(obj: BaseModel) -> Dict[str, FieldInfo]:
    if PYDANTIC_V2:
        return obj.model_fields
    else:
        return obj.__fields__  # type: ignore


def _get_model_config_field(obj: BaseModel, field_name: str) -> Optional[Any]:
    if PYDANTIC_V2:
        return obj.model_config.get(field_name)
    else:
        return getattr(obj.Config, field_name, None)  # type: ignore


def _model_iterate_fields(
    obj: Any, any_types: bool, loc: _Loc
) -> Iterator[Tuple[BaseModel, _Loc]]:
    if isinstance(obj, BaseModel):
        yield (obj, loc)
        any_types = (
            _get_model_config_field(obj, "arbitrary_types_allowed") or False
        )
        for field in _get_model_fields(obj):
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


if PYDANTIC_V2:
    from pydantic import ValidationError
    from pydantic_core import InitErrorDetails, PydanticCustomError

    def model_validate_extra_fields(root_model: BaseModel) -> None:
        errors: List[InitErrorDetails] = []

        extra_error_type = PydanticCustomError(
            "extra_forbidden", "Extra inputs are not permitted"
        )

        for model, loc in _model_iterate_fields(root_model, False, ()):

            for key, value in (model.model_extra or {}).items():
                errors.append(
                    {
                        "type": extra_error_type,
                        "loc": loc + (key,),
                        "input": value,
                    }
                )

        if errors:
            raise ValidationError.from_exception_data(
                type(root_model).__name__, errors
            )

else:
    from pydantic.v1.error_wrappers import ErrorWrapper, ValidationError
    from pydantic.v1.errors import ExtraError

    def model_validate_extra_fields(root_model: BaseModel) -> None:
        errors: List[ErrorWrapper] = []

        for model, loc in _model_iterate_fields(root_model, False, ()):
            declared = set(_get_model_fields(model).keys())
            for key in model.__dict__:
                if key not in declared:
                    errors.append(ErrorWrapper(ExtraError(), loc=loc + (key,)))

        if errors:
            raise ValidationError(errors, root_model.__class__)  # type: ignore
