from typing import List

from aidial_sdk import HTTPException as DIALException
from aidial_sdk.chat_completion import Message


def sanitize_namespace(namespace: str) -> str:
    return "".join(c if c.isalnum() or c in "._-/" else "-" for c in namespace)


def get_last_attachment_url(messages: List[Message]) -> str:
    for message in reversed(messages):
        if (
            message.custom_content is not None
            and message.custom_content.attachments is not None
        ):
            attachments = message.custom_content.attachments

            if attachments == []:
                continue

            if len(attachments) != 1:
                msg = "Only one attachment per message is supported"
                raise DIALException(
                    status_code=422,
                    message=msg,
                    display_message=msg,
                )

            attachment = attachments[0]

            url = attachment.url
            if url is None:
                msg = "Attachment is expected to be provided via a URL"
                raise DIALException(
                    status_code=422,
                    message=msg,
                    display_message=msg,
                )

            return url

    msg = "No attachment was found"
    raise DIALException(
        status_code=422,
        message=msg,
        display_message=msg,
    )
