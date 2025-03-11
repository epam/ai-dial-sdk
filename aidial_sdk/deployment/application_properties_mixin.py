from json import loads, JSONDecodeError
from typing import Dict, Any, Optional
from urllib.parse import urljoin

from aidial_sdk.exceptions import HTTPException as DIALException
from starlette.datastructures import MutableHeaders
from aidial_sdk.utils.pydantic import ExtraForbidModel

class ApplicationPropertiesMixin(ExtraForbidModel):
    application_properties: Optional[Dict[str, Any]] = None

    @classmethod
    async def get_application_properties(cls, headers: MutableHeaders, api_key: str, base_url: Optional[str]) -> Optional[Dict[str, Any]]:
        application_properties = ApplicationPropertiesMixin.get_application_properties_from_headers(headers)
        if not application_properties:
            application_properties = await cls.get_application_properties_from_core(headers, api_key, base_url)
        return application_properties

    @staticmethod
    def get_application_properties_from_headers(headers: MutableHeaders) -> Optional[Dict[str, Any]]:
        props_header = headers.get("X-DIAL-APPLICATION-PROPERTIES")
        if props_header:
            try:
                return loads(props_header)
            except JSONDecodeError as e:
                raise DIALException(
                    status_code=400,
                    type="invalid_request_error",
                    message=f"The X-APPLICATION-PROPERTIES header isn't valid JSON: {e.msg}",
                )

    @staticmethod
    async def get_application_properties_from_core(headers: MutableHeaders, api_key: str, base_url: Optional[str]) -> Optional[Dict[str, Any]]:
        dial_app_id = headers.get("X-DIAL-APPLICATION-ID")
        if headers.get("X-DIAL-APPLICATION-PROPERTIES") or not dial_app_id:
            return None

        if not base_url:
            raise ValueError("Base URL is required to make a request. Pls set one in DIALApp")

        try:
            import httpx
        except ImportError:
            raise DIALException(
                status_code=500,
                type="dependency_error",
                message="Httpx is not installed. Please install it as extras dependency."
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method="GET",
                    url=urljoin(urljoin(base_url, "/openai/applications/"), dial_app_id),
                    headers={"api-key": api_key}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            raise DIALException(
                status_code=500,
                type="internal_request_error",
                message=f"Error while fetching application (app_id {dial_app_id})properties: {e}")