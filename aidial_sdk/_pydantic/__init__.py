"""
The entry point for all Pydantic definition that unifies v1 and v2 APIs for SDK internals.

It's private, since its's expected that the client of the SDK
will either import `aidial_sdk.pydantic_v1` or `pydantic`.

This is the only place where `pydantic` imports
are allowed in the DIAL SDK package.
"""

# ruff: noqa: F401

import sys
from collections.abc import Mapping
from typing import TYPE_CHECKING

from pydantic import VERSION

from aidial_sdk.utils.env import env_bool

INSTALLED_PYDANTIC_V2 = VERSION.startswith("2.")
USE_PYDANTIC_V2 = env_bool("PYDANTIC_V2", False)

# Pydantic V1 (including the pydantic.v1 shim in pydantic>=2) is not
# compatible with Python 3.14+.  Force V2 mode automatically when running
# on Python 3.14+ so that users don't have to set PYDANTIC_V2=1 manually.
_PYTHON_314_OR_LATER = sys.version_info >= (3, 14)

PYDANTIC_V2 = INSTALLED_PYDANTIC_V2 and (
    USE_PYDANTIC_V2 or _PYTHON_314_OR_LATER
)

if TYPE_CHECKING:
    from pydantic import (
        BaseModel,
        Field,
        PositiveInt,
        SecretStr,
        StrictBool,
        StrictInt,
        StrictStr,
        ValidationError,
        model_validator,
    )
    from pydantic import ConfigDict as ConfigDict
    from pydantic import field_validator as validator
    from pydantic._internal._model_construction import ModelMetaclass
    from pydantic.fields import FieldInfo

    HeadersType = Mapping[str, str]
else:
    if PYDANTIC_V2:
        from typing import Annotated

        from pydantic import (
            BaseModel,
            ConfigDict,
            Field,
            PositiveInt,
            SecretStr,
            SkipValidation,
            StrictBool,
            StrictInt,
            StrictStr,
            ValidationError,
            model_validator,
        )
        from pydantic import field_validator as validator
        from pydantic._internal._model_construction import ModelMetaclass
        from pydantic.fields import FieldInfo

        # In Pydantic V2, skip validation to preserve the case-insensitive MutableHeaders object
        HeadersType = Annotated[Mapping[str, str], SkipValidation]
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

        def _fail(*args, **kwargs):
            raise ImportError("ConfigDict is only supported in Pydantic v2")

        ConfigDict = _fail

        HeadersType = Mapping[str, str]
