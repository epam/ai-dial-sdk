from json import loads, JSONDecodeError
from typing import Optional, Dict, Any
from urllib.parse import urljoin

from aidial_sdk.pydantic_v1 import StrictStr

from aidial_sdk.deployment.from_request_mixin import (
    ExtraForbidRequestWithAuthAndApplicationProperties,
)
from aidial_sdk.exceptions import HTTPException as DIALException


class SchemaRichApplicationsMixin(ExtraForbidRequestWithAuthAndApplicationProperties):
    @property
    def unreliable_dial_application_properties(
        self,
    ) -> Optional[Dict[str, Any]]:
        props_header = self.headers.get(
            StrictStr("X-DIAL-APPLICATION-PROPERTIES")
        )
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
    def dial_application_id(self) -> Optional[str]:
        return self.headers.get(StrictStr("X-DIAL-APPLICATION-ID"))

    async def request_dial_application_properties(
        self,
    ) -> Optional[Dict[str, Any]]:
        if self.unreliable_dial_application_properties:
            return self.unreliable_dial_application_properties

        if not self.dial_application_id:
            raise DIALException(
                status_code=400,
                type="invalid_request_error",
                message=f"The X-DIAL-APPLICATION-ID header isn't set",
            )

        if not self.base_url:
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
                    url=urljoin(
                        self.base_url,
                        f"/openai/applications/{self.dial_application_id}",
                    ),
                    headers={"api-key": self.api_key_secret.get_secret_value()},
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
                message=f"Error while fetching application (app_id {self.dial_application_id})properties: {e}",
            )
