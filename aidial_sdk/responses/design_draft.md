# DIAL Responses API SDK — API design draft

> Status: **design proposal, not implemented**.
> The protocol-level decisions this design depends on are collected in
> [Protocol decisions we need](#protocol-decisions-we-need) — everything else in
> this document is settled by the SDK surface alone.

- [Goals](#goals)
- [Mental model](#mental-model)
- [Quickstart](#quickstart)
- [Public surface](#public-surface)
- [Registering a deployment](#registering-a-deployment)
- [The request](#the-request)
- [The response](#the-response)
  - [Lifecycle and invariants](#lifecycle-and-invariants)
  - [Message item](#message-item)
  - [Stage item](#stage-item)
  - [Reasoning item](#reasoning-item)
  - [Function call item](#function-call-item)
  - [Custom tool call item](#custom-tool-call-item)
  - [Raw items](#raw-items)
  - [Response-level fields](#response-level-fields)
- [Streaming and the wire](#streaming-and-the-wire)
- [Errors](#errors)
- [Forms](#forms)
- [Worked examples](#worked-examples)
- [Migration cheat sheet](#migration-cheat-sheet)
- [Protocol decisions we need](#protocol-decisions-we-need)
- [Implementation plan](#implementation-plan)

---

## Goals

1. **Familiarity.** Somebody who knows `aidial_sdk.chat_completion` should be able
   to write a Responses application without reading anything but the cheat sheet.
   Same import layout, same `(request, response)` handler shape, same `with`-block
   builders, same `runtime_error` guard rails.
2. **The SDK owns the bookkeeping.** `sequence_number`, `output_index`,
   `content_index`, item `id`s, `response.created` / `response.completed`, the
   `output_item.added` → deltas → `output_item.done` ordering, and the final
   response snapshot are never the application's problem. This is the single
   biggest reason the SDK exists: the Responses wire format is far more
   bookkeeping-heavy than chat completion chunks.
3. **First-class support for what is unique to Responses**: a flat, ordered list
   of heterogeneous output items, reasoning items, custom tool calls, refusals and
   text annotations (citations), and per-item statuses.
4. **First-class support for what is unique to DIAL**: stages, files
   (ex-attachments), state, form schemas, per-model usage, cache breakpoints.
5. **Forward compatibility.** Unknown input item types must not break an
   application, and an application must be able to emit an item type the SDK does
   not model yet.

Non-goals for v1: `background`, `previous_response_id`, `conversation`,
server-side `store`, and the `/tokenize` / `/truncate_prompt` deployment
endpoints (their request bodies are chat-completion shaped).

---

## Mental model

The single structural difference from chat completion is that **there are no
choices**. A chat completion response is `n` parallel choices, each of which
accumulates content, stages, attachments and tool calls. A Responses response is
**one ordered list of output items**, and everything — the assistant message, each
stage, each tool call, the reasoning — *is* an item in that list.

So `Choice` disappears and `Response` itself becomes the container:

| chat completion | responses |
|---|---|
| `response.create_single_choice()` → `Choice` | `Response` is the container; no intermediate object |
| `choice.append_content(str)` | `message.append_text(str)` on a message item |
| `choice.create_stage(name)` | `response.create_stage(name)` |
| `choice.add_attachment(...)` | `message.add_file(...)` / `stage.add_file(...)` |
| `choice.set_state(dict)` | `response.set_state(dict)` |
| `choice.set_form_schema(dict)` | `response.set_form_schema(dict)` |
| `choice.create_function_tool_call(...)` | `response.create_function_call(...)` |
| `choice.close(finish_reason)` | per-item `close()`; response status is derived |
| `response.set_usage(prompt_tokens, completion_tokens)` | `response.set_usage(input_tokens, output_tokens)` |

Two consequences worth internalising:

- **Ordering is meaningful and observable.** `output_index` is assigned when an
  item is created, and the list preserves that order. A stage that runs before the
  answer genuinely precedes the answer in `output`, instead of living in a side
  channel.
- **Method names follow wire field names.** `message.append_text` (wire:
  `output_text.text`), `stage.append_content` (wire: `stage.content`),
  `function_call.append_arguments` (wire: `function_call.arguments`),
  `custom_tool_call.append_input` (wire: `custom_tool_call.input`). When you are
  unsure what a method is called, name the field.

---

## Quickstart

The echo application from the [README](../../README.md), ported. It is the same
length as the chat completion version.

```python
# Save this as app.py
import uvicorn

from aidial_sdk import DIALApp
from aidial_sdk.responses import Request, Response, Responses


# Responses is an abstract class for applications and model adapters
class EchoApplication(Responses):
    async def responses(self, request: Request, response: Response) -> None:
        # Get the last message (the newest) from the history
        last_message = request.messages[-1]

        # Generate a response with a single assistant message item
        with response.create_message() as message:
            # Fill the message with the last user's text
            message.append_text(last_message.text())

            # Echo back whatever files came in
            for file in last_message.files():
                message.add_file(file)


app = DIALApp()
app.add_responses("echo", EchoApplication())

if __name__ == "__main__":
    uvicorn.run(app, port=5000)
```

```sh
curl http://127.0.0.1:5000/openai/deployments/echo/responses \
  -H "Content-Type: application/json" \
  -H "Api-Key: DIAL_API_KEY" \
  -d '{"input": "Repeat me!"}'
```

```json
{
  "id": "resp_d08cfda2d7c8476f8b95424195fcdafe",
  "object": "response",
  "created_at": 1695298034,
  "model": "echo",
  "status": "completed",
  "output": [
    {
      "id": "msg_1f0c2a...",
      "type": "message",
      "role": "assistant",
      "status": "completed",
      "content": [{"type": "output_text", "text": "Repeat me!", "annotations": []}]
    }
  ],
  "usage": null
}
```

---

## Public surface

`aidial_sdk.responses` mirrors the layout of `aidial_sdk.chat_completion`:

```python
from aidial_sdk.responses import (
    # entry points
    Responses,              # the abstract application class
    Request,                # the parsed request (pydantic)
    Response,               # the response builder

    # output item builders (returned by Response factory methods)
    Message,
    Stage,
    Reasoning,
    FunctionCall,
    CustomToolCall,
    TextPart,

    # enums
    ItemStatus,             # in_progress | completed | incomplete
    ResponseStatus,         # completed | incomplete | failed
    IncompleteReason,       # max_output_tokens | content_filter
    Status,                 # stage status: completed | failed  (same as chat_completion)

    # request models
    File,
    CustomContent,
    InputMessage,           # alias: Message is the *output* builder, InputMessage the request model
    InputTextPart, InputImagePart, InputFilePart, InputAudioPart,
    OutputTextPart, RefusalPart,
    FunctionCallItem, FunctionCallOutputItem,
    CustomToolCallItem, CustomToolCallOutputItem,
    ReasoningItem, ItemReference, RawItem,
    Tool, FunctionTool, CustomTool, ToolChoice,
    TextConfig, ReasoningConfig,
    RequestCustomFields, CacheBreakpoint,

    # shared with chat completion
    CacheBreakpointPath,
    Annotation, UrlCitation, FileCitation,
)
```

> Naming collision to be aware of: `Message` is the **output builder**, while the
> request-side model is `InputMessage`. `request.messages` returns
> `list[InputMessage]`. The alternative (`OutputMessage` for the builder) was
> rejected because the builder is what applications type most often, and in
> `chat_completion` the short name likewise belongs to the builder (`Stage` vs
> `RequestStage`).

Forms move to a protocol-neutral module and are re-exported from both packages:

```python
from aidial_sdk.forms import Button, form, FormMetaclass     # new canonical location
from aidial_sdk.chat_completion import Button, FormMetaclass # kept as alias
from aidial_sdk.responses import Button, form, FormMetaclass # re-export
```

## Registering a deployment

```python
class Responses(ABC):
    @abstractmethod
    async def responses(self, request: Request, response: Response) -> None:
        """Implement the response generation logic"""

    async def rate_response(self, request: RateRequest) -> None: ...
    async def configuration(
        self, request: ConfigurationRequest
    ) -> ConfigurationResponse | dict: ...
```

```python
app = DIALApp()
app.add_responses(
    "my-app",
    MyApplication(),
    heartbeat_interval=25,   # same semantics as add_chat_completion
)
```

`add_responses` registers:

| route | when |
|---|---|
| `POST /openai/deployments/{name}/responses` | always |
| `POST /openai/deployments/{name}/rate` | always |
| `GET  /openai/deployments/{name}/configuration` | if `configuration` is overridden |

A deployment may serve both protocols; a class can implement both ABCs, and both
`add_chat_completion` and `add_responses` may be called for the same name.

```python
class MyApplication(ChatCompletion, Responses): ...

app.add_chat_completion("my-app", impl)
app.add_responses("my-app", impl)
```

`DIAL_SDK_SSE_HEARTBEAT_INTERVAL`, `DIAL_SDK_HEADERS_TO_PROXY`, telemetry,
`propagate_auth_headers` and the disconnect middleware all apply unchanged.

---

## The request

`Request` extends `FromRequestDeploymentMixin` exactly like the chat completion
one, so `request.api_key`, `request.headers`, `request.deployment_id`,
`request.base_url`, `request.conversation_id`,
`request.request_dial_application_properties()` etc. are all available unchanged.

```python
class ResponsesRequest(ExtraAllowModel):
    # --- OpenAI Responses API ---
    model: StrictStr | None = None
    input: StrictStr | list[InputItem]
    instructions: StrictStr | None = None

    tools: list[Tool] | None = None
    tool_choice: Literal["auto", "none", "required"] | ToolChoice | None = None
    parallel_tool_calls: StrictBool | None = None
    max_tool_calls: PositiveInt | None = None

    stream: StrictBool = False
    stream_options: StreamOptions | None = None

    text: TextConfig | None = None            # {"format": {...}, "verbosity": ...}
    reasoning: ReasoningConfig | None = None  # {"effort": ..., "summary": ...}

    temperature: Temperature | None = None
    top_p: TopP | None = None
    top_logprobs: StrictInt | None = None
    max_output_tokens: PositiveInt | None = None
    truncation: Literal["auto", "disabled"] | None = None
    include: list[StrictStr] | None = None
    metadata: dict[StrictStr, StrictStr] | None = None
    user: StrictStr | None = None
    prompt_cache_key: StrictStr | None = None
    safety_identifier: StrictStr | None = None

    # --- stateful features DIAL does not support (see below) ---
    store: StrictBool | None = None
    background: StrictBool | None = None
    previous_response_id: StrictStr | None = None
    conversation: StrictStr | ConversationRef | None = None

    # --- DIAL extensions ---
    max_prompt_tokens: PositiveInt | None = None
    custom_fields: RequestCustomFields | None = None   # configuration, cache_breakpoint
```

**Unsupported stateful fields.** `previous_response_id`, `background` and
`conversation` are rejected by the SDK at parse time with a
`RequestValidationError` (HTTP 422) before the handler runs; `store` is accepted
and ignored (a stateless deployment simply never stores). DIAL Core should reject
these earlier, but the SDK must not silently produce a wrong answer. An adapter
that genuinely implements them opts out per deployment:

```python
app.add_responses("stateful-app", impl, allow_stateful_fields=True)
```

### Input items

`input` is either a string or a heterogeneous list. The union is discriminated on
`type`, **with a catch-all**:

```python
InputItem = (
    InputMessage                  # {"type": "message", ...} — and the legacy
                                  # {"role": ..., "content": ...} shape with no "type"
    | FunctionCallItem            # {"type": "function_call", ...}
    | FunctionCallOutputItem      # {"type": "function_call_output", ...}
    | CustomToolCallItem          # {"type": "custom_tool_call", ...}
    | CustomToolCallOutputItem    # {"type": "custom_tool_call_output", ...}
    | ReasoningItem               # {"type": "reasoning", ...}
    | ItemReference               # {"type": "item_reference", "id": ...}
    | RawItem                     # anything else, preserved verbatim
)
```

`RawItem` is a deliberate difference from `chat_completion`, where an unknown
message shape is a validation error. Responses grows new built-in tool item types
(`web_search_call`, `image_generation_call`, `mcp_call`, …) faster than this SDK
can track them, and an adapter is usually expected to pass them through:

```python
class RawItem(ExtraAllowModel):
    type: StrictStr
    raw: dict[str, Any]   # the item exactly as received

    def id(self) -> str | None: ...
```

```python
class InputMessage(ExtraAllowModel):
    type: Literal["message"] = "message"
    role: Role                     # system | developer | user | assistant
    content: StrictStr | list[InputContentPart]
    status: ItemStatus | None = None
    id: StrictStr | None = None

    # DIAL extensions
    custom_content: CustomContent | None = None
    custom_fields: MessageCustomFields | None = None   # cache_breakpoint

    def text(self) -> str: ...
    def files(self) -> list[File]: ...
    def images(self) -> list[InputImagePart]: ...
```

```python
InputContentPart = (
    InputTextPart      # {"type": "input_text",  "text": ...}
    | InputImagePart   # {"type": "input_image", "image_url": ..., "detail": ...}
    | InputFilePart    # {"type": "input_file",  "file_url"|"file_data"|"file_id", "filename"}
    | InputAudioPart   # {"type": "input_audio", "input_audio": {...}}
    | OutputTextPart   # {"type": "output_text", "text": ..., "annotations": [...]}  (assistant history)
    | RefusalPart      # {"type": "refusal", "refusal": ...}
    | RawItem
)
```

> `InputMessage.text()` intentionally differs from
> `chat_completion.Message.text()`. In chat completion, `text()` raises when the
> content is a list of parts, because a string content is the common case there. In
> Responses, a list of parts is the common case, so `text()` returns the
> concatenation of all `input_text` / `output_text` parts and `""` when there are
> none. It never raises. Use `message.content` directly when you care about the
> structure.

### Navigation helpers

The `input` list mixes messages with tool traffic, so the SDK provides the
accessors that every application would otherwise write by hand (see
`examples/tic_tac_toe/app/request.py` for the chat completion equivalent):

```python
request.input_items          # list[InputItem] — a bare string is normalised to
                             # [InputMessage(role="user", content=[InputTextPart(...)])]
request.messages             # list[InputMessage] — only "message" items, in order
request.user_messages        # list[InputMessage] — role == "user"

request.state                # dict | None  — custom_content.state of the last assistant message
request.form_value           # Any  | None  — the form value submitted by the user
request.configuration        # dict | None  — custom_fields.configuration
```

`request.form_value` and `request.state` deliberately hide *where* those values
live on the wire (see [Protocol decisions](#protocol-decisions-we-need)): whether
a filled form arrives as `custom_content.form_value` on the last user message or
as a `custom_tool_call_output` item is an adapter concern, not an application
concern.

### Files

`File` is the Responses-era `Attachment`, renamed field by field:

```python
class File(ExtraAllowModel):
    filename: StrictStr | None = None       # was: title
    file_data: StrictStr | None = None      # was: data (+ type, as a data: URI)
    file_url: StrictStr | None = None       # was: url
    file_type: StrictStr | None = None      # was: type — only meaningful with file_url
    reference_url: StrictStr | None = None  # DIAL extension, unchanged
    reference_type: StrictStr | None = None # DIAL extension, unchanged
```

`InputMessage.files()` is the union of two sources, normalised into `File`:
native `input_file` / `input_image` content parts, and
`custom_content.files` of assistant messages echoed back from history.

---

## The response

### Lifecycle and invariants

```python
async def responses(self, request: Request, response: Response) -> None: ...
```

The SDK drives the protocol around the handler:

1. `response.created` and `response.in_progress` are emitted before the handler
   body runs (in streaming mode).
2. Every output item the handler creates is appended to `output` in creation order
   and assigned the next `output_index`.
3. When the handler returns, every still-open item is closed, the terminal event
   (`response.completed` / `response.incomplete`) is emitted with the complete
   response snapshot, and the stream ends.
4. If the handler raises, the response fails — see [Errors](#errors).

Item builders follow the `chat_completion` conventions exactly:

- `create_*()` returns an unopened builder; `open()` emits
  `response.output_item.added`; `close()` emits the item's `.done` events.
- The builders are context managers: `with response.create_message() as m:` opens
  on entry and closes on a clean exit. `Stage` additionally closes with
  `Status.FAILED` when the block exits with an exception, like today.
- Calling `append_*` / `add_*` on an unopened or closed builder raises a
  `runtime_error`, with the same message style as chat completion
  (`"Trying to append text to a closed message"`).
- `await response.aflush()` waits until everything queued so far has been written
  to the socket, unchanged from chat completion.

**Several items may be open at once**, and their deltas may interleave — this is
legal in the protocol, because every delta event carries its own `item_id` and
`output_index`. It is what makes "keep a stage open while the answer streams"
expressible:

```python
stage = response.create_stage("Searching")
stage.open()

with response.create_message() as message:
    message.append_text("Let me look that up. ")
    ...
    stage.append_content("found 12 documents")
    stage.close()
    message.append_text("Here is what I found: ...")
```

### Message item

```python
class Message:
    id: str
    output_index: int

    # sugar for the single-text-part case (content_index 0)
    def append_text(self, text: str) -> None: ...
    @property
    def content_stream(self) -> ContentStream: ...   # print(..., file=...), tqdm, logging

    # explicit multi-part content
    def create_text_part(self) -> TextPart: ...
    def append_refusal(self, refusal: str) -> None: ...

    # citations on the current text part
    def add_annotation(self, annotation: Annotation) -> None: ...
    def add_url_citation(
        self, url: str, *, title: str | None = None,
        start_index: int | None = None, end_index: int | None = None,
    ) -> None: ...

    # DIAL extensions
    def add_file(self, file: File) -> None: ...
    def add_file(
        self, *, filename: str | None = None, file_data: str | None = None,
        file_url: str | None = None, file_type: str | None = None,
        reference_url: str | None = None, reference_type: str | None = None,
    ) -> None: ...

    def open(self) -> None: ...
    def close(self, status: ItemStatus = ItemStatus.COMPLETED) -> None: ...
```

`append_text` writes into an implicit first `output_text` part, created on the
first call — this is what keeps the echo example three lines long and mirrors
`choice.append_content`. `create_text_part()` exists for the rare adapter that
must reproduce several content parts with correct `content_index` values:

```python
class TextPart:
    content_index: int
    def append_text(self, text: str) -> None: ...
    def add_annotation(self, annotation: Annotation) -> None: ...
    @property
    def content_stream(self) -> ContentStream: ...
    def open(self) -> None: ...
    def close(self) -> None: ...
```

`add_annotation` is the protocol-native way to attach citations, and it is what
DIAL RAG-style applications should reach for first; `add_file` remains the way to
return a payload (an image, a generated document, a markdown snippet) rather than
a reference.

### Stage item

The DIAL stage keeps its chat completion API verbatim — only its owner changes
from `Choice` to `Response`:

```python
stage = response.create_stage(name=None)

class Stage:
    def append_name(self, name: str) -> None: ...
    def append_content(self, content: str) -> None: ...
    @property
    def content_stream(self) -> ContentStream: ...
    def add_file(self, ...) -> None: ...          # same overloads as Message.add_file
    def open(self) -> None: ...
    def close(self, status: Status = Status.COMPLETED) -> None: ...
```

```python
with response.create_stage("Downloading the document") as stage:
    documents = loader.load()
    stage.append_content(f"Loaded {len(documents)} pages")
```

Its wire representation is the one genuinely contested protocol point; see
[Stages on the wire](#1-stages-on-the-wire). The SDK surface above holds under
either answer.

### Reasoning item

```python
with response.create_reasoning() as reasoning:
    reasoning.append_summary("The user asks about X, so I will ...")
    reasoning.set_encrypted_content(blob)     # for adapters that must round-trip it
```

```python
class Reasoning:
    def append_summary(self, text: str) -> None: ...   # implicit first summary part
    def create_summary_part(self) -> TextPart: ...     # explicit summary_index control
    def append_text(self, text: str) -> None: ...      # reasoning.content[], when the
                                                       # upstream exposes raw reasoning
    def set_encrypted_content(self, content: str) -> None: ...
    def open(self) -> None: ...
    def close(self, status: ItemStatus = ItemStatus.COMPLETED) -> None: ...
```

Adapters that receive a `ReasoningItem` in `input` and must replay it upstream do
not need this builder — they pass the parsed item straight through.

### Function call item

```python
with response.create_function_call(name="get_weather") as call:
    call.append_arguments('{"city":')
    call.append_arguments('"Paris"}')

print(call.call_id)   # generated when not supplied
```

```python
class FunctionCall:
    id: str
    call_id: str
    def append_arguments(self, arguments: str) -> None: ...
    def open(self) -> None: ...
    def close(self, status: ItemStatus = ItemStatus.COMPLETED) -> None: ...
```

`response.create_function_call(name, *, call_id=None, arguments=None)` — passing
`arguments` emits the whole call in one shot, for the non-streaming upstream case.

Note there is no `finish_reason` to set: in Responses, "the model wants to call a
tool" is expressed by a `function_call` item existing in `output`, and
`status: "completed"`. This removes the whole `_last_finish_reason` bookkeeping
that `chat_completion.Choice` carries.

### Custom tool call item

The Responses-only free-form tool call. One candidate encoding for DIAL forms
uses it (see [decision 3](#3-forms-custom_contentform_schema-vs-custom_tool_call)):

```python
with response.create_custom_tool_call(name="dial:forms") as call:
    call.append_input(json.dumps(schema))
```

```python
class CustomToolCall:
    id: str
    call_id: str
    def append_input(self, input: str) -> None: ...
    def open(self) -> None: ...
    def close(self, status: ItemStatus = ItemStatus.COMPLETED) -> None: ...
```

### Raw items

An escape hatch for item types the SDK does not model — built-in tool calls an
adapter proxies from an upstream model, or anything added to the protocol after
this SDK release:

```python
response.add_raw_item({
    "type": "image_generation_call",
    "status": "completed",
    "result": base64_png,
})
```

Emits `output_item.added` + `output_item.done` around a verbatim item (the SDK
fills in `id` if absent) and includes it in the final snapshot. There is
deliberately no streaming variant: an application that needs to stream a
non-modelled item type should ask for it to be modelled.

### Response-level fields

```python
# usage
response.set_usage(
    input_tokens=120,
    output_tokens=42,
    *,
    cached_tokens=64,        # -> input_tokens_details.cached_tokens
    reasoning_tokens=8,      # -> output_tokens_details.reasoning_tokens
)
response.add_usage_per_model("gpt-5", input_tokens=120, output_tokens=42)

# DIAL statistics
response.set_discarded_input_items([0, 1, 2])   # was: set_discarded_messages

# DIAL custom content
response.set_state({"board": ...})
response.set_form_schema(MyForm.model_json_schema())

# terminal status
response.set_incomplete(IncompleteReason.MAX_OUTPUT_TOKENS)

# envelope
response.set_response_id("resp_...")
response.set_created(1695298034)
response.set_model("gpt-5-2025-08-07")

# transport
response.append_header("X-My-Header", "value")
response.set_cache_breakpoint(
    cache_breakpoint_path=CacheBreakpointPath.input_items(3),
    cache_expire_at=...,
    cache_metadata=...,
)

# introspection
response.stream          # bool
response.items           # tuple[ItemBuilder, ...] created so far
await response.aflush()
```

Guard rails match chat completion: `set_response_id` / `set_created` /
`set_model` raise once generation has started; `set_usage`, `set_state`,
`set_form_schema` and `set_discarded_input_items` raise on a second call. Unlike
chat completion, `set_usage` does **not** require all output to be finished — the
Responses `usage` field lives on the response snapshot, which is only serialised
at the end anyway.

`CacheBreakpointPath` gains `input_items(idx)` (`prefix.body.input[{idx}]`)
alongside the existing `messages(idx)` and `tools(idx)`.

---

## Streaming and the wire

The SDK maintains the full response snapshot as items are built, because
`response.completed` must carry it. Block mode therefore falls out for free:
**the same builder calls, with intermediate events suppressed, and the snapshot
returned as the body.** No chunk merging — the `merge_chunks` machinery that
chat completion needs for `stream: false` has no counterpart here.

| SDK call | emitted events (streaming) |
|---|---|
| handler entry | `response.created`, `response.in_progress` |
| `message.open()` | `response.output_item.added` (`message`, `in_progress`) |
| `message.append_text(t)` (first) | `response.content_part.added` (`output_text`), `response.output_text.delta` |
| `message.append_text(t)` | `response.output_text.delta` |
| `message.add_url_citation(...)` | `response.output_text.annotation.added` |
| `message.append_refusal(r)` | `response.content_part.added` (`refusal`), `response.refusal.delta` |
| `message.close()` | `response.output_text.done`, `response.content_part.done`, `response.output_item.done` |
| `reasoning.append_summary(t)` | `response.reasoning_summary_part.added`, `response.reasoning_summary_text.delta` |
| `reasoning.close()` | `…summary_text.done`, `…summary_part.done`, `response.output_item.done` |
| `function_call.open()` | `response.output_item.added` (`function_call`) |
| `function_call.append_arguments(a)` | `response.function_call_arguments.delta` |
| `function_call.close()` | `response.function_call_arguments.done`, `response.output_item.done` |
| `custom_tool_call.append_input(i)` | `response.custom_tool_call_input.delta` |
| `response.add_raw_item(d)` | `response.output_item.added`, `response.output_item.done` |
| `response.set_usage(...)` / `set_state(...)` / `set_form_schema(...)` | nothing immediately; folded into the terminal snapshot |
| handler return | `response.completed` (or `response.incomplete`) |
| handler raises | `response.failed` |

`sequence_number` is a single monotonic counter owned by `Response`, incremented
per emitted event. `output_index` is assigned at `create_*()` time.
`content_index` is per item. Item ids are generated with the conventional
prefixes (`msg_`, `rs_`, `fc_`, `ctc_`, …) unless the application supplies one.

SSE framing follows the Responses convention — a named event plus a JSON payload
whose `type` repeats the name — rather than chat completion's bare `data:` lines:

```
event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":6,"item_id":"msg_1","output_index":0,"content_index":0,"delta":"Hello"}

```

Heartbeats keep working as today: `: heartbeat` comments injected after
`heartbeat_interval` seconds of idleness, which are legal SSE comments and are
ignored by the OpenAI clients.

---

## Errors

A raised exception has two shapes depending on how far generation has gone, which
is the same rule chat completion follows today:

**Nothing has been written yet** (always the case for `stream: false`, and for
`stream: true` before the first event is flushed): the SDK returns a regular DIAL
HTTP error body, so `HTTPException.json_error()` is unchanged.

```json
{"error": {"message": "...", "type": "invalid_request_error", "code": "400", "display_message": "..."}}
```

**The stream has already started**: the SDK closes every open item as
`incomplete`, then emits a terminal failure event carrying the DIAL error object:

```
event: response.failed
data: {"type":"response.failed","sequence_number":21,"response":{"id":"resp_1","object":"response","status":"failed","output":[…],"error":{"message":"…","type":"runtime_error","code":"500","display_message":"…"}}}

```

Non-DIAL exceptions become a `RuntimeServerError` with the generic message and are
logged, exactly as in `Response._run_producer` today. `display_message` and the
DIAL-specific extra fields ride along inside `response.error`.

> The alternative is OpenAI's standalone `event: error`. `response.failed` is
> proposed instead because it is the terminal event of the response state machine —
> clients that track status get a consistent final state, and the partial `output`
> is preserved. See [Protocol decisions](#4-streaming-error-event).

---

## Forms

The form *definition* side is unchanged — `Button`, the `form` decorator and
`FormMetaclass` are protocol-neutral and simply move to `aidial_sdk.forms`.

The DIAL-specific plumbing stays behind two calls:

```python
# server -> client: publish the schema the user should fill in
response.set_form_schema(MoveForm.model_json_schema())

# client -> server: read back what the user submitted
if form_value := request.form_value:
    move = MoveForm.model_validate(form_value)
```

Whether that travels as `custom_content.form_schema` on the assistant message or
as a `custom_tool_call` named `dial:forms` is invisible to the application. If
the `custom_tool_call` encoding wins, `set_form_schema` becomes sugar over
`create_custom_tool_call("dial:forms")` and `request.form_value` reads the
matching `custom_tool_call_output`; applications do not change.

---

## Worked examples

### 1. RAG with stages, citations and files

Ported from `examples/langchain_rag`, extended with the Responses-native pieces.

```python
from aidial_sdk import DIALApp
from aidial_sdk import HTTPException as DIALException
from aidial_sdk.responses import Message, Request, Response, Responses


class CustomCallbackHandler(AsyncCallbackHandler):
    def __init__(self, message: Message):
        self._message = message

    async def on_llm_new_token(self, token: str, *args, **kwargs) -> None:
        self._message.append_text(token)


class SimpleRAGApplication(Responses):
    async def responses(self, request: Request, response: Response) -> None:
        user_query = request.messages[-1].text()

        files = [f for m in request.messages for f in m.files()]
        if not files:
            raise DIALException(
                status_code=400,
                message="No document was provided",
                display_message="Please attach a document to your question.",
            )

        # Stages are output items now: they appear in `output` *before* the answer.
        with response.create_stage("Downloading the document") as stage:
            documents = load(files[-1])
            stage.append_content(f"{len(documents)} pages")

        with response.create_stage("Calculating embeddings"):
            docsearch = index(documents)

        with response.create_message() as message:
            await response.aflush()

            result = await qa.ainvoke(
                {"query": user_query},
                callbacks=[CustomCallbackHandler(message)],
            )

            # Protocol-native citations
            for doc in result["source_documents"]:
                message.add_url_citation(
                    url=doc.metadata["source"],
                    title=doc.metadata.get("title"),
                )

            # ...and the raw snippets as files, the way DIAL RAG does today
            for doc in result["source_documents"]:
                message.add_file(
                    filename=doc.metadata.get("title", "chunk"),
                    file_data=f"data:text/markdown,{doc.page_content}",
                    reference_url=doc.metadata["source"],
                )

        response.set_usage(input_tokens=..., output_tokens=...)
```

### 2. Text-to-image, returning a file

Ported from `examples/render_text`.

```python
class RenderTextApplication(Responses):
    async def responses(self, request: Request, response: Response) -> None:
        text = request.messages[-1].text()
        image_base64 = text_to_image_base64(text)

        with response.create_message() as message:
            message.add_file(
                filename="Image",
                file_data=f"data:image/png;base64,{image_base64}",
            )
            message.append_text(
                f"![Image](data:image/png;base64,{image_base64})"
            )
```

### 3. A configurable application with forms

Ported from `examples/tic_tac_toe` — note how much request-side boilerplate the
navigation helpers remove.

```python
class TicTacToeApplication(Responses):
    async def configuration(self, request):
        return InitConfiguration.model_json_schema()

    async def responses(self, request: Request, response: Response) -> None:
        init_conf = InitConfiguration.model_validate(request.configuration)

        if len(request.messages) == 1:
            board, user_move = Board(), None
        else:
            user_move = Move.from_button_value(
                MoveForm.model_validate(request.form_value).move
            )
            board = Board.model_validate(request.state)

        outcome = self.make_bot_move(board, init_conf.player, user_move)

        with response.create_message() as message:
            message.append_text(outcome.bot_response)
            if outcome.show_board:
                message.append_text("\n\n" + outcome.board.to_markdown())

        if not outcome.board.finished:
            move_selector = Field(
                description="Available moves",
                buttons=[
                    Button(title=m.print(), const=m.to_button_value(), submit=True)
                    for m in outcome.board.possible_moves
                ],
            )
            response.set_form_schema(
                form(move=move_selector)(MoveForm).model_json_schema()
            )

        response.set_state(outcome.board.model_dump())
```

### 4. A model adapter: reasoning, tool calls, pass-through

The shape an `ai-dial-responses-adapter` would take.

```python
class UpstreamAdapter(Responses):
    async def responses(self, request: Request, response: Response) -> None:
        upstream = await call_upstream(request)

        async for event in upstream:
            if event.type == "reasoning_summary":
                with response.create_reasoning() as reasoning:
                    reasoning.append_summary(event.text)

            elif event.type == "text":
                with response.create_message() as message:
                    async for delta in event.deltas:
                        message.append_text(delta)

            elif event.type == "tool_call":
                with response.create_function_call(
                    name=event.name, call_id=event.call_id
                ) as call:
                    async for delta in event.deltas:
                        call.append_arguments(delta)

            else:
                # built-in tool calls the SDK does not model yet
                response.add_raw_item(event.raw)

        if upstream.truncated:
            response.set_incomplete(IncompleteReason.MAX_OUTPUT_TOKENS)

        response.set_usage(
            input_tokens=upstream.usage.input_tokens,
            output_tokens=upstream.usage.output_tokens,
            cached_tokens=upstream.usage.cached_tokens,
            reasoning_tokens=upstream.usage.reasoning_tokens,
        )
        response.add_usage_per_model(
            upstream.model,
            input_tokens=upstream.usage.input_tokens,
            output_tokens=upstream.usage.output_tokens,
        )
```

---

## Migration cheat sheet

| chat completion | responses |
|---|---|
| `from aidial_sdk.chat_completion import ChatCompletion, Request, Response` | `from aidial_sdk.responses import Responses, Request, Response` |
| `async def chat_completion(self, request, response)` | `async def responses(self, request, response)` |
| `app.add_chat_completion(name, impl)` | `app.add_responses(name, impl)` |
| `request.messages` | `request.messages` (only `message` items) / `request.input_items` (everything) |
| `message.text()` raises on part lists | `message.text()` concatenates text parts |
| `message.custom_content.attachments` | `message.files()` |
| `request.custom_fields.configuration` | `request.configuration` |
| dig out `custom_content.state` by hand | `request.state` |
| dig out `custom_content.form_value` by hand | `request.form_value` |
| `with response.create_single_choice() as choice:` | `with response.create_message() as message:` |
| `choice.append_content(t)` | `message.append_text(t)` |
| `choice.content_stream` | `message.content_stream` |
| `choice.add_attachment(type=…, title=…, data=…, url=…)` | `message.add_file(file_type=…, filename=…, file_data=…, file_url=…)` |
| — | `message.add_url_citation(url=…, title=…)` |
| `choice.create_stage(name)` | `response.create_stage(name)` |
| `stage.append_content` / `append_name` / `add_attachment` | `stage.append_content` / `append_name` / `add_file` |
| `choice.set_state` / `set_form_schema` | `response.set_state` / `set_form_schema` |
| `choice.create_function_tool_call(id, name, args)` | `response.create_function_call(name, call_id=…, arguments=…)` |
| `choice.create_function_call(name, args)` (legacy) | — (dropped; Responses has no `function_call` field) |
| `choice.close(FinishReason.LENGTH)` | `response.set_incomplete(IncompleteReason.MAX_OUTPUT_TOKENS)` |
| `FinishReason.TOOL_CALLS` | implied by a `function_call` item in `output` |
| `response.set_usage(prompt_tokens, completion_tokens)` | `response.set_usage(input_tokens, output_tokens)` |
| `response.add_usage_per_model(model, prompt_tokens, completion_tokens)` | `response.add_usage_per_model(model, input_tokens, output_tokens)` |
| `response.set_discarded_messages([…])` | `response.set_discarded_input_items([…])` |
| `CacheBreakpointPath.messages(i)` | `CacheBreakpointPath.input_items(i)` |
| `n > 1` | not applicable — no choices |
| `tokenize` / `truncate_prompt` endpoints | not in v1 |

---

## Protocol decisions we need

Everything above is settled by the SDK surface. These four are wire-format choices
the SDK cannot make on its own; each one is invisible to applications, so the
review can land the SDK surface first and these later.

### 1. Stages on the wire

- **Option A — a dedicated output item type** (`{"type": "dial.stage", "name":
  …, "status": …, "content": …, "files": […]}`) with matching
  `response.dial.stage.*` streaming events. Ordering relative to text is exact,
  nothing needs merge semantics, and the item carries its own status. Risk: a
  strict OpenAI-typed client may reject an unknown `output` item type or an
  unknown SSE event name. **This needs verifying against `openai-python` and
  `openai-node` before it can be recommended.**
- **Option B — `custom_content.stages` on the assistant message's `output_text`
  part**, streamed as `response.output_text.delta` events with an empty `delta`
  and a `custom_content` payload. Extra
  fields on known objects are preserved by the OpenAI clients, so this is the safe
  choice, and it maps 1:1 to `choice.custom_content.stages` for chat completion
  conversion. Costs: stage ordering is implicit, indices must be merged, and the
  SDK has to lazily open a carrier message item when a stage precedes any text.

**Recommendation: B for v1**, A once client leniency is confirmed. Under B,
`response.create_stage()` before any message opens a hidden carrier message item
that stays open until the response ends.

### 2. Where DIAL response-level extensions live

`state`, `form_schema` and `files` are per-message in chat completion
(`choice.custom_content`). In Responses they are per-response concepts, and the
SDK exposes them that way (`response.set_state`). The wire choice is
`custom_content` on the assistant message's `output_text` part
(conversion-friendly) versus a top-level `custom_content` on the response object
(simpler, but a new top-level field). Same question for `statistics`
(`usage_per_model`, `discarded_input_items`), which chat completion puts at the
top level.

**Recommendation:** `statistics` top-level (matching chat completion), `state` /
`form_schema` / `files` inside the message's `output_text.custom_content`
(required for chat-completion conversion).

### 3. Forms: `custom_content.form_schema` vs `custom_tool_call`

Modelling forms as a `custom_tool_call` named `dial:forms` is elegant — it makes
the form round-trip a first-class part of the item list and gives the filled
value a natural home
(`custom_tool_call_output`). It also requires the client to send
`tools: [{"type": "custom", "name": "dial:forms"}]` to opt in, which is a
behaviour change for DIAL Chat. `custom_content.form_schema` is the
zero-migration option.

**Recommendation:** `custom_content.form_schema` for v1 parity;
revisit `dial:forms` when DIAL Chat is ready. Either way `set_form_schema` /
`request.form_value` are the only application-visible API.

### 4. Streaming error event

`response.failed` (proposed above) versus OpenAI's standalone `event: error`
versus chat completion's bare `data: {"error": …}`. DIAL Core, DIAL Chat and the
analytics pipeline must all agree. **Recommendation: `response.failed` with the
DIAL error object in `response.error`**, because it keeps the response state
machine consistent and preserves the partial `output`.

### 5. Smaller open items

- **Endpoint shape.** `POST /openai/deployments/{name}/responses` is what the SDK
  registers. Does Core also expose the OpenAI-native `POST /v1/responses` with
  `model` in the body, and if so does the SDK need to serve it?
- **Handler name.** `responses` (chosen, matches `chat_completion` /
  `embeddings`) vs `create_response` (reads better in isolation).
- **`discarded_input_items` vs `discarded_messages`** as the `statistics` field
  name. The indices point into `input`, so the former is proposed.
- **`file_type`**. Redundant when `file_data` is a data URI, needed alongside
  `file_url`. Keep it, or require the type to be carried by the URL?
- **`tokenize` / `truncate_prompt`.** Their DIAL request bodies embed
  chat-completion requests. Out of v1; a Responses-shaped variant would need its
  own protocol work.

---

## Implementation plan

The chat completion package maps onto this design closely enough that most files
have a direct counterpart, which keeps the work reviewable in small pieces.

| step | deliverable | verify |
|---|---|---|
| 1 | `responses/request.py` — models, `RawItem` fallback, navigation helpers, stateful-field rejection | round-trip tests over recorded OpenAI Responses payloads; unknown item types survive |
| 2 | `responses/events.py` — the event dataclasses (counterpart of `chat_completion/chunks.py`), owning `sequence_number` / index assignment | golden-file tests: builder call sequence → exact SSE transcript |
| 3 | `responses/response.py` + item builders, snapshot accumulation | the same handler produces a consistent snapshot in `stream: true` and `stream: false`; guard-rail errors |
| 4 | `responses/base.py`, `DIALApp.add_responses`, heartbeats, error paths | end-to-end tests through `TestClient`, streaming and block; error before/after first flush |
| 5 | `aidial_sdk.forms` extraction + re-exports | existing chat completion form tests unchanged |
| 6 | ported `examples/echo` and `examples/langchain_rag`, README section | run them against a local DIAL |

Two implementation notes worth fixing now:

- **The snapshot is the source of truth.** Items write into the accumulating
  response object and *derive* events from those writes, rather than the chat
  completion arrangement where chunks are the source of truth and the block
  response is merged back out of them. This removes `merge_chunks` /
  `cleanup_indices` from the Responses path entirely and guarantees streaming and
  block modes agree by construction.
- **Wire mapping behind one seam.** Given the open protocol questions, the
  translation from builder writes to events should sit in a single module
  (`events.py`) with no application-visible surface, so that resolving
  [decision 1](#1-stages-on-the-wire) or
  [decision 3](#3-forms-custom_contentform_schema-vs-custom_tool_call) is a change
  in one file and not an SDK-wide migration.
