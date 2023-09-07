from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseChunk(ABC):
    @abstractmethod
    def to_dict(self):
        pass


class StartChoiceChunk(BaseChunk):
    choice_index: int

    def __init__(self, choice_index: int):
        self.choice_index = choice_index

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {"role": "assistant"},
                }
            ],
            "usage": None,
        }


class EndChoiceChunk(BaseChunk):
    finish_reason: str
    index: int
    timestamp: int

    def __init__(self, finish_reason="stop", index: int = 0):
        self.finish_reason = finish_reason
        self.index = index

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.index,
                    "finish_reason": self.finish_reason,
                    "delta": {},
                }
            ],
            "usage": None,
        }


class ContentChunk(BaseChunk):
    content: str
    choice_index: int

    def __init__(self, content: str, choice_index: int):
        self.content = content
        self.choice_index = choice_index

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {"content": self.content},
                }
            ],
            "usage": None,
        }


class StartStageChunk(BaseChunk):
    choice_index: int
    stage_index: int

    def __init__(self, choice_index: int, stage_index: int, name: str):
        self.choice_index = choice_index
        self.stage_index = stage_index
        self.name = name

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {
                        "custom_content": {
                            "stages": [
                                {
                                    "index": self.stage_index,
                                    "name": self.name,
                                    "status": None,
                                }
                            ]
                        }
                    },
                }
            ],
            "usage": None,
        }


class FinishStageChunk(BaseChunk):
    choice_index: int
    stage_index: int
    status: str

    def __init__(self, choice_index: int, stage_index: int, status: str):
        self.choice_index = choice_index
        self.stage_index = stage_index
        self.status = status

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {
                        "custom_content": {
                            "stages": [
                                {
                                    "index": self.stage_index,
                                    "status": self.status,
                                }
                            ]
                        }
                    },
                }
            ],
            "usage": None,
        }


class ContentStageChunk(BaseChunk):
    choice_index: int
    stage_index: int
    content: str

    def __init__(self, choice_index: int, stage_index: int, content: str):
        self.choice_index = choice_index
        self.stage_index = stage_index
        self.content = content

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {
                        "custom_content": {
                            "stages": [
                                {
                                    "index": self.stage_index,
                                    "content": self.content,
                                    "status": None,
                                }
                            ]
                        }
                    },
                }
            ],
            "usage": None,
        }


class AttachmentStageChunk(BaseChunk):
    choice_index: int
    stage_index: int
    attachment_index: int

    type: Optional[str]
    title: Optional[str]
    data: Optional[str]
    url: Optional[str]
    reference_url: Optional[str]
    reference_type: Optional[str]

    def __init__(
        self,
        choice_index: int,
        stage_index: int,
        attachment_index: int,
        type: Optional[str] = None,
        title: Optional[str] = None,
        data: Optional[str] = None,
        url: Optional[str] = None,
        reference_url: Optional[str] = None,
        reference_type: Optional[str] = None,
    ):
        self.choice_index = choice_index
        self.stage_index = stage_index
        self.attachment_index = attachment_index

        self.type = type
        self.title = title
        self.data = data
        self.url = url
        self.reference_url = reference_url
        self.reference_type = reference_type

    def to_dict(self):
        result = {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {
                        "custom_content": {
                            "stages": [
                                {
                                    "index": self.stage_index,
                                    "attachments": [
                                        {"index": self.attachment_index}
                                    ],
                                    "status": None,
                                }
                            ]
                        }
                    },
                }
            ],
            "usage": None,
        }

        attachment = result["choices"][0]["delta"]["custom_content"]["stages"][
            0
        ]["attachments"][0]
        if self.type:
            attachment["type"] = self.type
        if self.title:
            attachment["title"] = self.title
        if self.data:
            attachment["data"] = self.data
        if self.url:
            attachment["url"] = self.url
        if self.reference_url:
            attachment["reference_url"] = self.reference_url
        if self.reference_type:
            attachment["reference_type"] = self.reference_type

        return result


class StateChunk(BaseChunk):
    choice_index: int
    state: Any

    def __init__(self, choice_index: int, state: Any):
        self.state = state
        self.choice_index = choice_index

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {"custom_content": {"state": self.state}},
                }
            ],
            "usage": None,
        }


class AttachmentChunk(BaseChunk):
    choice_index: int
    attachment_index: int

    type: Optional[str]
    title: Optional[str]
    data: Optional[str]
    url: Optional[str]
    reference_url: Optional[str]
    reference_type: Optional[str]

    def __init__(
        self,
        choice_index: int,
        attachment_index: int,
        type: Optional[str] = None,
        title: Optional[str] = None,
        data: Optional[str] = None,
        url: Optional[str] = None,
        reference_url: Optional[str] = None,
        reference_type: Optional[str] = None,
    ):
        self.choice_index = choice_index
        self.attachment_index = attachment_index
        self.type = type
        self.title = title
        self.data = data
        self.url = url
        self.reference_url = reference_url
        self.reference_type = reference_type

    def to_dict(self):
        result = {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {
                        "custom_content": {
                            "attachments": [{"index": self.attachment_index}]
                        }
                    },
                }
            ],
            "usage": None,
        }

        attachment = result["choices"][0]["delta"]["custom_content"][
            "attachments"
        ][0]
        if self.type:
            attachment["type"] = self.type
        if self.title:
            attachment["title"] = self.title
        if self.data:
            attachment["data"] = self.data
        if self.url:
            attachment["url"] = self.url
        if self.reference_url:
            attachment["reference_url"] = self.reference_url
        if self.reference_type:
            attachment["reference_type"] = self.reference_type

        return result


class UsageChunk(BaseChunk):
    prompt_tokens: int
    completion_tokens: int

    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

    def to_dict(self):
        return {
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.prompt_tokens + self.completion_tokens,
            }
        }


class UsagePerModelChunk(BaseChunk):
    index: int
    model: str
    prompt_tokens: int
    completion_tokens: int

    def __init__(
        self,
        index: int,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ):
        self.index = index
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

    def to_dict(self):
        return {
            "statistics": {
                "usage_per_model": [
                    {
                        "index": self.index,
                        "model": self.model,
                        "prompt_tokens": self.prompt_tokens,
                        "completion_tokens": self.completion_tokens,
                        "total_tokens": self.prompt_tokens
                        + self.completion_tokens,
                    }
                ]
            }
        }


class EndChunk:
    pass
