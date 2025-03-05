from typing import TYPE_CHECKING

from pydantic import StrictStr

from aidial_sdk.pydantic._compat import PYDANTIC_V2

if TYPE_CHECKING:
    from pydantic import Field
else:
    if PYDANTIC_V2:
        from pydantic import Field
    else:
        from pydantic.v1 import Field

from aidial_sdk.deployment.from_request_mixin import FromRequestBasicMixin


class RateRequest(FromRequestBasicMixin):
    response_id: StrictStr = Field(None, alias="responseId")
    rate: bool = False
