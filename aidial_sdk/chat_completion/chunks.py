from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional, TypedDict

from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.chat_completion.enums import FinishReason, Status
from aidial_sdk.exceptions import HTTPException as DIALException
from aidial_sdk.utils.json import remove_nones


class BaseChunk(ABC):
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass


class DefaultChunk(TypedDict, total=False):
    id: str
    model: str
    created: int
    object: str


class BaseChunkWithDefaults:
    chunk: BaseChunk
    defaults: DefaultChunk

    def __init__(self, chunk: BaseChunk, defaults: DefaultChunk):
        self.chunk = chunk
        self.defaults = defaults

    def to_dict(self, *, with_defaults: bool) -> Dict[str, Any]:
        if with_defaults:
            return {**self.chunk.to_dict(), **self.defaults}
        else:
            return self.chunk.to_dict()


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


class FunctionToolCallChunk(BaseChunk):
    choice_index: int
    call_index: int
    id: Optional[str]
    type: Optional[Literal["function"]]
    name: Optional[str]
    arguments: Optional[str]

    def __init__(
        self,
        choice_index: int,
        call_index: int,
        id: Optional[str],
        type: Optional[Literal["function"]],
        name: Optional[str],
        arguments: Optional[str],
    ):
        self.choice_index = choice_index
        self.call_index = call_index
        self.id = id
        self.type = type
        self.name = name
        self.arguments = arguments

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {
                        "content": None,
                        "tool_calls": [
                            remove_nones(
                                {
                                    "index": self.call_index,
                                    "id": self.id,
                                    "type": self.type,
                                    "function": remove_nones(
                                        {
                                            "name": self.name,
                                            "arguments": self.arguments,
                                        }
                                    ),
                                }
                            )
                        ],
                    },
                }
            ],
            "usage": None,
        }


class FunctionCallChunk(BaseChunk):
    choice_index: int
    name: Optional[str]
    arguments: Optional[str]

    def __init__(
        self,
        choice_index: int,
        name: Optional[str],
        arguments: Optional[str],
    ):
        self.choice_index = choice_index
        self.name = name
        self.arguments = arguments

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {
                        "content": None,
                        "function_call": remove_nones(
                            {
                                "name": self.name,
                                "arguments": self.arguments,
                            }
                        ),
                    },
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


class FormSchemaChunk(BaseChunk):
    choice_index: int
    form_schema: str

    def __init__(self, choice_index: int, form_schema: Any):
        self.choice_index = choice_index
        self.form_schema = form_schema

    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {
                        "custom_content": {
                            "form_schema": self.form_schema,
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

    def attachment_dict(self) -> dict:
        attachment: Dict[str, Any] = {"index": self.attachment_index}

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


class PromptTokensDetails(TypedDict, total=False):
    cached_tokens: int


class AttachmentChunk(Attachment, BaseChunk):
    def to_dict(self):
        return {
            "choices": [
                {
                    "index": self.choice_index,
                    "finish_reason": None,
                    "delta": {
                        "custom_content": {
                            "attachments": [self.attachment_dict()]
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
                                    "attachments": [self.attachment_dict()],
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
    prompt_tokens_details: Optional[PromptTokensDetails]

    def __init__(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        prompt_tokens_details: Optional[PromptTokensDetails],
    ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.prompt_tokens_details = prompt_tokens_details

    def to_dict(self):
        return {
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.prompt_tokens + self.completion_tokens,
                **(
                    {"prompt_tokens_details": self.prompt_tokens_details}
                    if self.prompt_tokens_details
                    else {}
                ),
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
    discarded_messages: List[int]

    def __init__(self, discarded_messages: List[int]):
        self.discarded_messages = discarded_messages

    def to_dict(self):
        return {
            "statistics": {
                "discarded_messages": self.discarded_messages,
            }
        }


class ArbitraryChunk(BaseChunk):
    chunk: Dict[str, Any]

    def __init__(self, chunk: Dict[str, Any]):
        self.chunk = chunk

    def to_dict(self):
        return self.chunk


class ExceptionChunk:
    exc: DIALException

    def __init__(self, exc: DIALException):
        self.exc = exc


class EndChunk:
    pass
