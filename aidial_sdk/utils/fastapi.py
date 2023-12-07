from json import JSONDecodeError

from fastapi import Request

from aidial_sdk.exceptions import HTTPException as DIALException


async def get_request_body(request: Request) -> dict:
    try:
        return await request.json()
    except JSONDecodeError as e:
        raise DIALException(
            status_code=400,
            type="invalid_request_error",
            message=f"Your request contained invalid JSON: {str(e.msg)}",
        )
