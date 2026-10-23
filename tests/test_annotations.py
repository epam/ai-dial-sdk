import asyncio
import json
from copy import deepcopy

import pytest

from aidial_sdk.chat_completion import (
    ChatCompletion,
    Choice,
    CustomContent,
    Request,
    Response,
)
from aidial_sdk.chat_completion._types import ChunkQueue
from aidial_sdk.chat_completion.chunks import BaseChunk
from aidial_sdk.exceptions import RuntimeServerError
from tests.utils.client import create_app_client

ANNOTATIONS = [
    {
        "id": "source-1",
        "type": "citation",
        "title": "First source",
        "url": "https://example.com/1",
    },
    {
        "id": "source-2",
        "type": "citation",
        "title": "Second source",
        "url": "https://example.com/2",
    },
]


class AnnotationApplication(ChatCompletion):
    def __init__(self):
        self.history: CustomContent | None = None

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        self.history = request.messages[-1].custom_content
        with response.create_single_choice() as choice:
            choice.append_content('Answer <cit data-id="source-1">')
            for annotation in ANNOTATIONS:
                choice.add_annotation(annotation)


def test_annotations_round_trip():
    app = AnnotationApplication()
    with create_app_client(app) as client:
        result = client.post(
            "chat/completions",
            json={"messages": [{"role": "user", "content": "Question"}]},
        )
        assert result.status_code == 200
        message = result.json()["choices"][0]["message"]
        assert message["custom_content"]["annotations"] == ANNOTATIONS
        replay = client.post("chat/completions", json={"messages": [message]})
        assert replay.status_code == 200
        assert app.history is not None
        assert app.history.annotations == ANNOTATIONS


def test_annotations_streaming():
    with create_app_client(AnnotationApplication()) as client:
        response = client.post(
            "chat/completions",
            json={
                "messages": [{"role": "user", "content": "Question"}],
                "stream": True,
            },
        )
        assert response.status_code == 200
        annotations = []
        for line in response.iter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                chunk = json.loads(line[6:])
                annotations.extend(
                    chunk["choices"][0]["delta"]
                    .get("custom_content", {})
                    .get("annotations", [])
                )
        assert annotations == [
            {**annotation, "index": index}
            for index, annotation in enumerate(ANNOTATIONS)
        ]


@pytest.mark.parametrize(
    "annotations", [None, [], ANNOTATIONS, [{"index": 0, **ANNOTATIONS[0]}]]
)
def test_accept_annotations_in_history(annotations):
    with create_app_client(AnnotationApplication()) as client:
        response = client.post(
            "chat/completions",
            json={
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Answer",
                        "custom_content": {"annotations": annotations},
                    }
                ]
            },
        )
        assert response.status_code == 200


@pytest.mark.parametrize(
    "custom_content",
    [
        {"annotations": "invalid"},
        {"annotations": [1]},
        {"annotations": [], "unknown": True},
    ],
)
def test_annotations_do_not_disable_request_validation(custom_content):
    with create_app_client(AnnotationApplication()) as client:
        response = client.post(
            "chat/completions",
            json={
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Answer",
                        "custom_content": custom_content,
                    }
                ]
            },
        )
        assert response.status_code == 400


def test_annotation_indices_are_owned_by_each_choice():
    queue: ChunkQueue = asyncio.Queue()
    annotation = {**deepcopy(ANNOTATIONS[0]), "index": 99}
    for choice_index in range(2):
        with Choice(queue, choice_index) as choice:
            choice.add_annotation(annotation)
            choice.add_annotation(ANNOTATIONS[1])
    assert annotation["index"] == 99
    annotation["title"] = "Changed"
    chunks = []
    while not queue.empty():
        chunk = queue.get_nowait()
        assert isinstance(chunk, BaseChunk)
        chunks.append(chunk.to_dict())
    for choice_index in range(2):
        for index in range(2):
            item = chunks[choice_index * 4 + index + 1]["choices"][0]
            assert item["index"] == choice_index
            assert item["delta"]["custom_content"]["annotations"] == [
                {**ANNOTATIONS[index], "index": index}
            ]


@pytest.mark.parametrize("closed", [False, True])
def test_annotation_requires_open_choice(closed):
    queue: ChunkQueue = asyncio.Queue()
    choice = Choice(queue, 0)
    if closed:
        choice.open()
        choice.close()
    size = queue.qsize()
    with pytest.raises(RuntimeServerError):
        choice.add_annotation(ANNOTATIONS[0])
    assert queue.qsize() == size
