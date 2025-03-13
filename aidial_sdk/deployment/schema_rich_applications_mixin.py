from json import JSONDecodeError, loads
from typing import Any, Dict, Optional
from urllib.parse import urljoin

from aidial_sdk.deployment.from_request_mixin import (
    ExtraForbidRequestWithAuthAndApplicationProperties,
)
from aidial_sdk.exceptions import InternalServerError, InvalidRequestError
from aidial_sdk.pydantic_v1 import StrictStr
from aidial_sdk.utils.logging import log_debug


class SchemaRichApplicationsMixin(
    ExtraForbidRequestWithAuthAndApplicationProperties
):

    _DIAL_APPLICATION_PROPERTIES_HEADER = StrictStr(
        "X-DIAL-APPLICATION-PROPERTIES"
    )
    _DIAL_APPLICATION_ID_HEADER = StrictStr("X-DIAL-APPLICATION-ID")

    @property
    def unreliable_dial_application_properties(
        self,
    ) -> Optional[Dict[str, Any]]:
        props_header = self.headers.get(
            self._DIAL_APPLICATION_PROPERTIES_HEADER
        )
        if props_header:
            try:
                return loads(props_header)
            except JSONDecodeError:
                raise InvalidRequestError(
                    f"The value of {self._DIAL_APPLICATION_PROPERTIES_HEADER} header isn't valid JSON"
                )

    @property
    def dial_application_id(self) -> Optional[str]:
        return self.headers.get(self._DIAL_APPLICATION_ID_HEADER)

    async def request_dial_application_properties(
        self,
    ) -> Optional[Dict[str, Any]]:
        if self.unreliable_dial_application_properties:
            return self.unreliable_dial_application_properties

        if not self.dial_application_id:
            raise InvalidRequestError(
                f"The {self._DIAL_APPLICATION_ID_HEADER} header isn't set"
            )

        if not self.base_url:
            raise InternalServerError(
                f"Base DIALApp dial_url should be set to perform request_dial_application_properties invocation"
            )

        try:
            import httpx
        except ImportError:
            raise ValueError(
                "Missing httpx dependencies. "
                "Install the package with the extras: aidial-sdk[httpx]"
            )

        try:
            log_debug(
                f"Requesting application properties for {self.dial_application_id}"
            )
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
                properties_dictionary = response.json().get(
                    "application_properties"
                )
                log_debug(
                    f"Received application properties for {self.dial_application_id!r}: {properties_dictionary}"
                )
                return properties_dictionary
        except Exception as ex:
            raise InternalServerError(
                f"Unable to retrieve application properties for the application {self.dial_application_id!r}: {ex}",
            )
