from aidial_sdk.utils.env import env_var_list


def test_env_var_list_strips_whitespace(monkeypatch):
    monkeypatch.setenv("TEST_VAR", "a, b , c , ")
    assert env_var_list("TEST_VAR") == ["a", "b", "c"]
