from aidial_sdk.utils._content_stream import ContentStream


class DummyReceiver:
    def __init__(self):
        self.items = []

    def append_content(self, content: str) -> None:
        self.items.append(content)


def test_content_stream_write():
    receiver = DummyReceiver()
    stream = ContentStream(receiver)
    stream.write("hello")
    stream.write(" world")
    assert receiver.items == ["hello", " world"]
