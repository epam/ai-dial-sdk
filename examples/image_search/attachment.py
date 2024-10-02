from typing import List, Optional

from aidial_sdk.chat_completion import Message
from aidial_sdk.chat_completion.request import Attachment

DEFAULT_IMAGE_TYPES = ["image/jpeg", "image/png"]


def get_image_attachments(
    messages: List[Message], image_types: Optional[List[str]] = None
) -> List[Attachment]:
    if image_types is None:
        image_types = DEFAULT_IMAGE_TYPES

    attachments = []
    for message in messages:
        if (
            message.custom_content is not None
            and message.custom_content.attachments is not None
        ):
            attachments = message.custom_content.attachments
            for attachment in attachments:
                if (
                    # For simplicity of example let's take only images,
                    # that are uploaded to DIAL Storage already
                    attachment.url
                    and attachment.type
                    and attachment.type in image_types
                ):
                    attachments.append(attachment)

    return attachments
