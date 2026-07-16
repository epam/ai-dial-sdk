import pytest

from aidial_sdk.utils.env import env_json_dict


def test_env_json_dict_returns_parsed_value(monkeypatch):
    monkeypatch.setenv("X", '{"a": "%(levelname)s"}')
    assert env_json_dict("X", {"default": True}) == {"a": "%(levelname)s"}


def test_env_json_dict_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("X", raising=False)
    assert env_json_dict("X", {"default": True}) == {"default": True}


def test_env_json_dict_rejects_non_dict(monkeypatch):
    monkeypatch.setenv("X", "[1, 2]")
    with pytest.raises(ValueError) as exc:
        env_json_dict("X", {})
    assert str(exc.value) == (
        "The value of the 'X' environment variable is expected to be a "
        "valid JSON dictionary."
    )


def test_env_json_dict_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("X", "{not json}")
    with pytest.raises(ValueError) as exc:
        env_json_dict("X", {})
    assert str(exc.value) == (
        "The value of the 'X' environment variable is expected to be a "
        "valid JSON dictionary."
    )
