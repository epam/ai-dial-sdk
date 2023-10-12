from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from aidial_sdk.chat_completion.enums import FinishReason, Status
from aidial_sdk.pydantic_v1 import BaseModel, root_validator


class BaseChunk(ABC):
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
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
    finish_reason: FinishReason
    choice_index: int

    def __init__(self, finish_reason: FinishReason, choice_index: int):
        self.finish_reason = finish_reason
        self.choice_index = choice_index

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": self.finish_reason.value,
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
    name: Optional[str]

    def __init__(
        self, choice_index: int, stage_index: int, name: Optional[str]
    ):
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
    status: Status

    def __init__(self, choice_index: int, stage_index: int, status: Status):
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
                                    "status": self.status.value,
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


class NameStageChunk(BaseChunk):
    choice_index: int
    stage_index: int
    name: str

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


class Attachment(BaseModel):
    choice_index: int
    attachment_index: int

    type: Optional[str]
    title: Optional[str]
    data: Optional[str]
    url: Optional[str]
    reference_url: Optional[str]
    reference_type: Optional[str]

    @root_validator
    def check_data_or_url(cls, values):
        data, url = values.get("data"), values.get("url")

        if not data and not url:
            raise ValueError("Trying to add attachment without data and url")
        if data and url:
            raise ValueError("Trying to add attachment with data and url")

        return values

    def attachment_dict(self, index: int):
        attachment: Dict[str, Any] = {"index": index}

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

        return attachment


class AttachmentChunk(Attachment, BaseChunk):
    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {
                        "custom_content": {
                            "attachments": [
                                self.attachment_dict(self.attachment_index)
                            ]
                        }
                    },
                }
            ],
            "usage": None,
        }


class AttachmentStageChunk(Attachment, BaseChunk):
    stage_index: int

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
                                    "attachments": [
                                        self.attachment_dict(
                                            self.attachment_index
                                        )
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


class DiscardedMessagesChunk(BaseChunk):
    discarded_messages: int

    def __init__(self, discarded_messages: int):
        self.discarded_messages = discarded_messages

    def to_dict(self):
        return {
            "statistics": {
                "discarded_messages": self.discarded_messages,
            }
        }


class EndChunk:
    exc: Optional[Exception]

    def __init__(self, exc: Optional[Exception] = None):
        self.exc = exc
