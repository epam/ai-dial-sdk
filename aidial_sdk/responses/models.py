from typing import Any, Literal

from aidial_sdk._pydantic import Field
from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.responses.enums import (
    ErrorCode,
    IncompleteReason,
    ItemStatus,
    MessagePhase,
    ResponseStatus,
)


class UrlCitation(BaseModel):
    type: Literal["url_citation"] = "url_citation"
    url: str
    title: str
    start_index: int
    end_index: int


class FileCitation(BaseModel):
    type: Literal["file_citation"] = "file_citation"
    file_id: str
    filename: str
    index: int


class ContainerFileCitation(BaseModel):
    type: Literal["container_file_citation"] = "container_file_citation"
    container_id: str
    file_id: str
    filename: str
    start_index: int
    end_index: int


class FilePath(BaseModel):
    type: Literal["file_path"] = "file_path"
    file_id: str
    index: int


Annotation = UrlCitation | FileCitation | ContainerFileCitation | FilePath


class LogprobTopLogprob(BaseModel):
    token: str
    bytes: list[int]
    logprob: float


class Logprob(BaseModel):
    token: str
    bytes: list[int]
    logprob: float
    top_logprobs: list[LogprobTopLogprob]


class SearchSource(BaseModel):
    type: Literal["url"] = "url"
    url: str


class SearchAction(BaseModel):
    type: Literal["search"] = "search"
    query: str | None = None
    queries: list[str] | None = None
    sources: list[SearchSource] | None = None


class OpenPageAction(BaseModel):
    type: Literal["open_page"] = "open_page"
    url: str | None = None


class FindInPageAction(BaseModel):
    type: Literal["find_in_page"] = "find_in_page"
    url: str
    pattern: str


WebSearchAction = SearchAction | OpenPageAction | FindInPageAction


class InputTokensDetails(BaseModel):
    cached_tokens: int
    cache_write_tokens: int


class OutputTokensDetails(BaseModel):
    reasoning_tokens: int


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_tokens_details: InputTokensDetails
    output_tokens_details: OutputTokensDetails


# The response object and its output items and content parts, named after
# their openai types. The builders mutate them as the handler runs;
# events.py serialises them into event payloads. Every field the schema
# requires is present in a dump, even when empty.


class ResponseOutputText(BaseModel):
    type: Literal["output_text"] = "output_text"
    text: str = ""
    annotations: list[Annotation] = Field(default_factory=list)
    logprobs: list[Logprob] | None = None


class ResponseOutputRefusal(BaseModel):
    type: Literal["refusal"] = "refusal"
    refusal: str = ""


class ReasoningSummary(BaseModel):
    type: Literal["summary_text"] = "summary_text"
    text: str = ""


class ReasoningContent(BaseModel):
    type: Literal["reasoning_text"] = "reasoning_text"
    text: str = ""


ContentPart = ResponseOutputText | ResponseOutputRefusal | ReasoningContent


class ResponseOutputMessage(BaseModel):
    type: Literal["message"] = "message"
    id: str
    role: Literal["assistant"] = "assistant"
    status: ItemStatus = ItemStatus.IN_PROGRESS
    content: list[ResponseOutputText | ResponseOutputRefusal] = Field(
        default_factory=list
    )
    phase: MessagePhase | None = None


class ResponseReasoningItem(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    id: str
    status: ItemStatus = ItemStatus.IN_PROGRESS
    summary: list[ReasoningSummary] = Field(default_factory=list)
    content: list[ReasoningContent] | None = None
    encrypted_content: str | None = None


class ResponseFunctionToolCall(BaseModel):
    type: Literal["function_call"] = "function_call"
    id: str
    status: ItemStatus = ItemStatus.IN_PROGRESS
    call_id: str
    name: str
    arguments: str = ""


class ResponseCustomToolCall(BaseModel):
    # NOTE: the item has no `status` field at all
    type: Literal["custom_tool_call"] = "custom_tool_call"
    id: str
    call_id: str
    name: str
    input: str = ""


class ResponseFunctionWebSearch(BaseModel):
    type: Literal["web_search_call"] = "web_search_call"
    id: str
    status: Literal["in_progress", "searching", "completed", "failed"] = (
        "in_progress"
    )
    action: WebSearchAction = Field(default_factory=SearchAction)


class ImageGenerationCall(BaseModel):
    type: Literal["image_generation_call"] = "image_generation_call"
    id: str
    status: Literal["in_progress", "generating", "completed", "failed"] = (
        "in_progress"
    )
    result: str | None = None


ResponseOutputItem = (
    ResponseOutputMessage
    | ResponseReasoningItem
    | ResponseFunctionToolCall
    | ResponseCustomToolCall
    | ResponseFunctionWebSearch
    | ImageGenerationCall
)


class ResponseError(BaseModel):
    # Exactly the two fields of `ResponseError`: nothing else may appear
    code: ErrorCode
    message: str


class IncompleteDetails(BaseModel):
    reason: IncompleteReason


class ResponseObject(BaseModel):
    id: str
    object: Literal["response"] = "response"
    created_at: int
    model: str
    status: ResponseStatus = ResponseStatus.IN_PROGRESS
    output: list[ResponseOutputItem] = Field(default_factory=list)
    error: ResponseError | None = None
    incomplete_details: IncompleteDetails | None = None
    usage: Usage | None = None

    # Echoed request parameters the schema requires
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_choice: Literal["auto", "none", "required"] | dict[str, Any] = "auto"
    parallel_tool_calls: bool = True

    # Echoed request parameters, null when the request has none
    instructions: str | None = None
    max_output_tokens: int | None = None
    max_tool_calls: int | None = None
    metadata: dict[str, str] | None = None
    prompt_cache_key: str | None = None
    reasoning: dict[str, Any] | None = None
    safety_identifier: str | None = None
    temperature: float | None = None
    text: dict[str, Any] | None = None
    top_logprobs: int | None = None
    top_p: float | None = None
    truncation: Literal["auto", "disabled"] | None = None
    user: str | None = None
