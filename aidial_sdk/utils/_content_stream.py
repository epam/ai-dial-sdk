from typing import Protocol


class ContentReceiver(Protocol):
    def append_content(self, content: str) -> None: ...


class ContentStream:
    """
    The ContentStream class allows using the receiver in contexts where typing.SupportsWrite[str] is expected.
    For example:

    1. Redirecting print statements:

        print("Hello, world", file=content_stream)

    2. Using with tqdm for progress bars:

        import tqdm
        for item in tqdm(items, file=content_stream):
            process(item)

    3. Redirecting logs to the content stream:

        import logging
        logging_handler = logging.StreamHandler(stream=content_stream)

    4. Writing CSV data:

        import csv
        csv.writer(content_stream).writerows(data)
    """

    _receiver: ContentReceiver

    def __init__(self, receiver: ContentReceiver) -> None:
        self._receiver = receiver

    def write(self, s: str) -> None:
        self._receiver.append_content(s)
