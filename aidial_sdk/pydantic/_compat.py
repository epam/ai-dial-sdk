from typing import TYPE_CHECKING

import pydantic

PYDANTIC_V2 = pydantic.VERSION.startswith("2.")

if TYPE_CHECKING:
    from pydantic import ConfigDict as ConfigDict
else:
    if PYDANTIC_V2:
        import warnings

        from pydantic import ConfigDict
        from pydantic.warnings import PydanticDeprecatedSince20

        # Suppress Pydantic deprecation warnings for extra kwargs in `Field`
        warnings.filterwarnings(
            "ignore",
            message=r"Using extra keyword arguments on `Field` is deprecated and will be removed. Use `json_schema_extra` instead. \(Extra keys: 'buttons'\).*",
            category=PydanticDeprecatedSince20,
        )

        warnings.filterwarnings(
            "ignore",
            message=r"Support for class-based `config` is deprecated, use ConfigDict instead.*",
            category=PydanticDeprecatedSince20,
        )
    else:
        ConfigDict = None
