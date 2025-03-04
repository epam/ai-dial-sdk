from typing import TYPE_CHECKING

import pydantic

PYDANTIC_V2 = pydantic.VERSION.startswith("2.")

if TYPE_CHECKING:
    from pydantic import ConfigDict as ConfigDict
else:
    if PYDANTIC_V2:
        from pydantic import ConfigDict
    else:

        def _fail(*args, **kwargs):
            raise ImportError("ConfigDict is only available in Pydantic 2")

        ConfigDict = _fail
