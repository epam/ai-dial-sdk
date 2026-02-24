from aidial_sdk.chat_completion import Message, Request


def get_message_form_value(message: Message) -> dict | None:
    cc = message.custom_content
    if cc is None:
        return None
    return cc.form_value


def get_message_state(message: Message) -> dict | None:
    cc = message.custom_content
    if cc is None:
        return None
    return cc.state


def get_configuration(request: Request) -> dict:
    cf = request.custom_fields
    assert cf is not None and cf.configuration is not None
    return cf.configuration
