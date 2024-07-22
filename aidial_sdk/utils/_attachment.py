from typing import Optional, cast, overload

from aidial_sdk.chat_completion.request import Attachment


@overload
def create_attachment(attachment: Attachment) -> Attachment: ...


@overload
def create_attachment(
    type: Optional[str] = None,
    title: Optional[str] = None,
    data: Optional[str] = None,
    url: Optional[str] = None,
    reference_url: Optional[str] = None,
    reference_type: Optional[str] = None,
) -> Attachment: ...


def create_attachment(*args, **kwargs) -> Attachment:
    if args and isinstance(args[0], Attachment):
        return cast(Attachment, args[0])
    elif isinstance(kwargs.get("attachment"), Attachment):
        return cast(Attachment, kwargs.get("attachment"))
    else:
        return _attachment_from_fields(*args, **kwargs)


def _attachment_from_fields(
    type: Optional[str] = None,
    title: Optional[str] = None,
    data: Optional[str] = None,
    url: Optional[str] = None,
    reference_url: Optional[str] = None,
    reference_type: Optional[str] = None,
) -> Attachment:
    return Attachment(
        type=type,
        title=title,
        data=data,
        url=url,
        reference_url=reference_url,
        reference_type=reference_type,
    )
