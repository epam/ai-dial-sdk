import random
from typing import List

from examples.tic_tac_toe.app import app
from tests.utils.client import create_test_client


def test_ttt_configuration():
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
                "enum": ["X", "O"],
                "type": "string",
                "dial:widget": "buttons",
                "oneOf": [
                    {
                        "const": "X",
                        "title": "𝕏",
                        "dial:widgetOptions": {
                            "confirmationMessage": "Are you sure you want to play as 𝕏? It goes first.",
                            "populateText": None,
                            "submit": True,
                        },
                    },
                    {
                        "const": "O",
                        "title": "Ⓞ",
                        "dial:widgetOptions": {
                            "confirmationMessage": "Are you sure you want to play as Ⓞ? It goes second.",
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
    client = create_test_client(app, name="app")

    init_conf = {"player": "X"}

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

    client = create_test_client(app, name="app")

    init_conf = {"player": "O"}

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
            [None, "X", None],
            [None, None, None],
            [None, None, None],
        ]
    }


def test_ttt_second_move_o():
    random.seed(42)

    client = create_test_client(app, name="app")

    init_conf = {"player": "O"}

    messages: List[dict] = [
        {
            "role": "user",
            "content": "",
        }
    ]

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
            "custom_content": {"form_value": {"move": "B2"}},
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
            ["X", "X", None],
            [None, "O", None],
            [None, None, None],
        ]
    }
