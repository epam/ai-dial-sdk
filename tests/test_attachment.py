import pytest

from aidial_sdk._pydantic import ValidationError
from aidial_sdk.chat_completion.request import Attachment
from tests.utils.pydantic import model_parse


def test_data_only():
    attachment = model_parse(Attachment, {"data": "base64..."})
    assert attachment.data == "base64..."
    assert attachment.url is None


def test_url_only():
    attachment = model_parse(Attachment, {"url": "https://example.com/file"})
    assert attachment.url == "https://example.com/file"
    assert attachment.data is None


def test_neither_data_nor_url_raises():
    with pytest.raises(
        ValidationError,
        match="Attachment must have either 'data' or 'url', but it's missing both",
    ):
        model_parse(Attachment, {})


def test_both_data_and_url_raises():
    with pytest.raises(
        ValidationError,
        match="Attachment must have either 'data' or 'url', but it has both",
    ):
        model_parse(
            Attachment, {"data": "base64...", "url": "https://example.com/file"}
        )
