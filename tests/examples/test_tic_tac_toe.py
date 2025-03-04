import random
from typing import List

import pytest

from aidial_sdk.pydantic._compat import PYDANTIC_V2
from tests.utils.client import create_test_client

pytestmark = pytest.mark.skipif(
    not PYDANTIC_V2, reason="The example is written using Pydantic V2"
)


def test_ttt_configuration():
    from examples.tic_tac_toe.app.main import app

    client = create_test_client(app, name="app")
    response = client.get("configuration")

    body = response.json()
    assert body == {
        "required": ["player"],
        "additionalProperties": False,
        "type": "object",
        "properties": {
            "player": {
                "title": "Player",
                "description": "Select tic-tac-toe player",
                "enum": [1, 2],
                "type": "number",
                "dial:widget": "buttons",
                "oneOf": [
                    {
                        "const": 1,
                        "title": "X",
                        "dial:widgetOptions": {
                            "confirmationMessage": "Are you sure you want to play as X? It goes first.",
                            "populateText": None,
                            "submit": True,
                        },
                    },
                    {
                        "const": 2,
                        "title": "O",
                        "dial:widgetOptions": {
                            "confirmationMessage": "Are you sure you want to play as O? It goes second.",
                            "populateText": None,
                            "submit": True,
                        },
                    },
                ],
            }
        },
        "title": "InitConfiguration",
        "dial:chatMessageInputDisabled": True,
    }


def test_ttt_first_move_x():
    from examples.tic_tac_toe.app.main import app

    client = create_test_client(app, name="app")

    init_conf = {"player": 1}

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": ""}],
            "custom_fields": {"configuration": init_conf},
        },
    )

    body = response.json()
    content = body["choices"][0]["message"]["content"]
    state = body["choices"][0]["message"]["custom_content"]["state"]

    assert (
        content.strip()
        == """
You go first. Make a move.

||A|B|C|
|---|---|---|---|
|3| | | |
|2| | | |
|1| | | |
""".strip()
    )
    assert state == {
        "cells": [
            [None, None, None],
            [None, None, None],
            [None, None, None],
        ]
    }


def test_ttt_first_move_o():
    random.seed(42)

    from examples.tic_tac_toe.app.main import app

    client = create_test_client(app, name="app")

    init_conf = {"player": 2}

    response = client.post(
        "chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "",
                }
            ],
            "custom_fields": {"configuration": init_conf},
        },
    )

    body = response.json()
    content = body["choices"][0]["message"]["content"]
    state = body["choices"][0]["message"]["custom_content"]["state"]

    assert (
        content.strip()
        == """
I moved to B1. Now it's your turn.

||A|B|C|
|---|---|---|---|
|3| | | |
|2| | | |
|1| |X| |
""".strip()
    )
    assert state == {
        "cells": [
            [None, 1, None],
            [None, None, None],
            [None, None, None],
        ]
    }


def test_ttt_second_move_o():
    random.seed(42)

    from examples.tic_tac_toe.app.main import app

    client = create_test_client(app, name="app")

    init_conf = {"player": 2}

    messages: List[dict] = [{"role": "user", "content": ""}]

    response = client.post(
        "chat/completions",
        json={
            "messages": messages,
            "custom_fields": {"configuration": init_conf},
        },
    )

    body = response.json()
    message = body["choices"][0]["message"]

    messages.append(message)
    messages.append(
        {
            "role": "user",
            "content": "",
            "custom_content": {"form_value": {"move": 22}},
        }
    )

    response = client.post(
        "chat/completions",
        json={
            "messages": messages,
            "custom_fields": {"configuration": init_conf},
        },
    )

    body = response.json()
    message = body["choices"][0]["message"]
    content = message["content"]
    state = message["custom_content"]["state"]

    assert (
        content.strip()
        == """
I moved to A1. Now it's your turn.

||A|B|C|
|---|---|---|---|
|3| | | |
|2| |O| |
|1|X|X| |
""".strip()
    )
    assert state == {
        "cells": [
            [1, 1, None],
            [None, 2, None],
            [None, None, None],
        ]
    }
