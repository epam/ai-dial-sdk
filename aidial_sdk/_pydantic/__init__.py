"""
The entry point for all Pydantic definition that unifies v1 and v2 APIs for SDK internals.

It's private, since its's expected that the client of the SDK
will either import `aidial_sdk.pydantic_v1` or `pydantic`.

This is the only place where `pydantic` imports
are allowed in the DIAL SDK package.
"""

from typing import TYPE_CHECKING

from pydantic import VERSION

from aidial_sdk.utils.env import env_bool

INSTALLED_PYDANTIC_V2 = VERSION.startswith("2.")
USE_PYDANTIC_V2 = env_bool("PYDANTIC_V2", False)
PYDANTIC_V2 = INSTALLED_PYDANTIC_V2 and USE_PYDANTIC_V2

if TYPE_CHECKING:
    from pydantic import BaseModel
    from pydantic import ConfigDict as ConfigDict
    from pydantic import (
        Field,
        PositiveInt,
        SecretStr,
        StrictBool,
        StrictInt,
        StrictStr,
        ValidationError,
    )
    from pydantic import field_validator as validator
    from pydantic import model_validator
    from pydantic._internal._model_construction import ModelMetaclass
    from pydantic.fields import FieldInfo
    from pydantic.v1.validators import make_literal_validator
else:

    if PYDANTIC_V2:
        from pydantic import (
            BaseModel,
            ConfigDict,
            Field,
            PositiveInt,
            SecretStr,
            StrictBool,
            StrictInt,
            StrictStr,
            ValidationError,
        )
        from pydantic import field_validator as validator
        from pydantic import model_validator
        from pydantic._internal._model_construction import ModelMetaclass
        from pydantic.fields import FieldInfo
        from pydantic.v1.validators import make_literal_validator
    else:
        from pydantic.v1 import (
            BaseModel,
            Field,
            PositiveInt,
            SecretStr,
            StrictBool,
            StrictInt,
            StrictStr,
            validator,
        )

        try:
            from pydantic.v1.main import ModelMetaclass
        except ImportError:
            from pydantic.main import ModelMetaclass
        from pydantic.v1 import ValidationError, root_validator
        from pydantic.v1.fields import FieldInfo
        from pydantic.v1.validators import make_literal_validator

        def _fail(*args, **kwargs):
            raise ImportError("ConfigDict is only supported in Pydantic v2")

        ConfigDict = _fail
