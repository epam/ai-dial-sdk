import warnings

from aidial_sdk._pydantic import PYDANTIC_V2

_WARN_MESSAGE_V1 = """"
The usage of `aidial_sdk.pydantic_v1` module is deprecated.

To migrate your code simply replace all `aidial_sdk.pydantic_v1` imports with `pydantic` imports.
""".strip()

_WARN_MESSAGE_V2 = """"
The usage of `aidial_sdk.pydantic_v1` module is deprecated.
This module provides Pydantic v1 model even when Pydantic v2 is installed. We recommend using Pydantic v2 models.

To migrate your code to Pydantic v2 models, you can follow these steps:

1. Replace all `aidial_sdk.pydantic_v1` imports with `pydantic` imports.
2. Migrate usages of Pydantic v1 models originating in DIAL SDK to Pydantic v2 API.
3. Set environment variable `PYDANTIC_V2=True` to make the DIAL SDK use Pydantic v2 models instead of Pydantic v1.
""".strip()

warnings.warn(
    _WARN_MESSAGE_V2 if PYDANTIC_V2 else _WARN_MESSAGE_V1, DeprecationWarning
)

try:
    from pydantic.v1 import *  # type: ignore
except ImportError:
    from pydantic import *  # type: ignore
