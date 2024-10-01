from typing import List

from aidial_sdk.chat_completion.request import Message, MessageContentTextPart


def get_message_text_content(message: Message) -> str:
    texts: List[str] = []

    content = message.content

    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, MessageContentTextPart):
                texts.append(part.text)

    return "\n".join(texts)
