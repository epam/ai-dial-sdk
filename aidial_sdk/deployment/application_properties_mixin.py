from abc import ABC, abstractmethod
from json import loads, JSONDecodeError
from typing import Optional, Dict, Any, Mapping
from urllib.parse import urljoin

from aidial_sdk.pydantic_v1 import StrictStr

from aidial_sdk.deployment.from_request_mixin import HasHeadersAndBaseUrl
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.utils.pydantic import ExtraForbidModel

class SchemaRichApplicationsMixin(HasHeadersAndBaseUrl, ExtraForbidModel):

    @abstractmethod
    def get_headers(self) -> Mapping[StrictStr, StrictStr]:
        ...

    @abstractmethod
    def get_base_url(self) -> Optional[str]:
        ...

    class Config:
        arbitrary_types_allowed = True

    @property
    def unreliable_dial_application_properties(self) -> Optional[Dict[str, Any]]:
        props_header = self.get_headers().get(StrictStr("X-DIAL-APPLICATION-PROPERTIES"))
        if props_header:
            try:
                return loads(props_header)
            except JSONDecodeError as e:
                raise DIALException(
                    status_code=400,
                    type="invalid_request_error",
                    message=f"The X-APPLICATION-PROPERTIES header isn't valid JSON: {e.msg}",
                )

    @property
    def get_application_id(self) -> str:
        return self.get_headers().get(StrictStr("X-DIAL-APPLICATION-ID"))

    async def request_dial_application_properties(self) -> Optional[Dict[str, Any]]:
        if self.unreliable_dial_application_properties:
            return self.unreliable_dial_application_properties

        if not self.get_application_id:
            raise DIALException(
                status_code=400,
                type="invalid_request_error",
                message=f"The X-DIAL-APPLICATION-ID header isn't set",
            )

        base_url = self.get_base_url()
        if not base_url:
            raise DIALException(
                status_code=500,
                type="dependency_error",
                message="Base url should be set to perform request_dial_application_properties invocation",
            )

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method="GET",
                    url=urljoin(base_url, f"/openai/applications/{self.dial_app_id}"),
                    headers={"api-key": self.api_key},
                )
                response.raise_for_status()
                return response.json().get("application_properties")
        except ImportError:
            raise DIALException(
                status_code=500,
                type="dependency_error",
                message="Httpx is not installed. Please install it as extras dependency.",
            )
        except Exception as e:
            raise DIALException(
                status_code=500,
                type="internal_request_error",
                message=f"Error while fetching application (app_id {self.dial_app_id})properties: {e}",
            )
