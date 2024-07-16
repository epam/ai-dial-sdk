import json

from aidial_sdk.chat_completion import Message, Role


def test_message_ser():
    msg_obj = Message(role=Role.SYSTEM, content="test")
    actual_dict = msg_obj.dict(exclude_none=True)
    expected_dict = {"role": "system", "content": "test"}

    assert json.loads(json.dumps(actual_dict)) == expected_dict


def test_message_deser():
    msg_dict = {"role": "system", "content": "test"}
    actual_obj = Message.parse_raw(json.dumps(msg_dict))
    expected_obj = Message(role=Role.SYSTEM, content="test")

    assert actual_obj == expected_obj
