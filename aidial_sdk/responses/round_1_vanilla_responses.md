# Round 1 — vanilla Responses API

> Part of the [Responses API SDK design](./design_draft.md). This round delivers a
> working, spec-compliant Responses endpoint with **no DIAL-specific features**.
> [Round 2](./round_2_dial_features.md) adds stages, files, state and forms;
> [round 3](./round_3_improvements.md) collects optional follow-ups.

- [Scope](#scope)
- [Quickstart](#quickstart)
- [Registering a deployment](#registering-a-deployment)
- [The request](#the-request)
- [The response](#the-response)
  - [What the builders produce](#what-the-builders-produce)
- [Streaming and the wire](#streaming-and-the-wire)
- [Errors](#errors)
- [Worked examples](#worked-examples)
- [Explicitly deferred](#explicitly-deferred)

---

## Scope

Everything needed for a DIAL deployment to serve `POST /responses` correctly for a
client that knows nothing about DIAL:

- the `Responses` ABC and `DIALApp.add_responses`
- the request model, including the full input-item union and a forward-compatible
  fallback for item types the SDK does not model
- the response builder and every output item type the Responses API defines:
  messages with text / refusal / annotation content, reasoning, function calls,
  custom tool calls
- streaming and block responses, with the SDK owning all protocol bookkeeping
- errors

A round-1 response payload contains no `custom_content` and no `statistics`
anywhere. That is the acceptance criterion for this round: diff a round-1 response
against an OpenAI Responses response and only the values should differ.

---

## Quickstart

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


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_responses("echo", EchoApplication())

# Run built app
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

## Registering a deployment

```python
class Responses(ABC):
    @abstractmethod
    async def responses(self, request: Request, response: Response) -> None:
        """Implement the response generation logic"""

    async def rate_response(self, request: RateRequest) -> None: ...
```

```python
app = DIALApp()
app.add_responses(
    "my-app",
    MyApplication(),
    heartbeat_interval=25,   # same semantics as add_chat_completion
)
```

`add_responses` registers `POST /openai/deployments/{name}/responses` and
`POST /openai/deployments/{name}/rate`. The `rate` handler is the chat completion
one, reused verbatim.

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

    # declared only so they can be rejected
    store: StrictBool | None = None
    background: StrictBool | None = None
    previous_response_id: StrictStr | None = None
    conversation: StrictStr | ConversationRef | None = None
```

Round 2 adds the DIAL request extensions (`max_prompt_tokens`, `custom_fields`).

**Stateful fields are rejected.** `previous_response_id`, `background`,
`conversation` and `store: true` fail at parse time with a
`RequestValidationError` (HTTP 422) before the handler runs. `store: false` and an
absent `store` are accepted, since that is what a stateless deployment does.

There is no opt-out flag. A DIAL application cannot serve these fields — there is
no response store to read `previous_response_id` from and no place to park a
`background` response — so a per-deployment escape hatch would only let a
deployment claim support it does not have. DIAL Core should reject these earlier
too; the SDK check is the backstop that keeps an application from silently
answering a question it was not asked.

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

    def text(self) -> str: ...
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

Round 2 adds `custom_content` / `custom_fields` to `InputMessage` and a
`files()` accessor that normalises `input_file` parts and DIAL's
`custom_content.files` into one list.

### Navigation helpers

The `input` list mixes messages with tool traffic, so the SDK provides the
accessors every application would otherwise write by hand:

```python
request.input_items          # list[InputItem] — a bare string is normalised to
                             # [InputMessage(role="user", content=[InputTextPart(...)])]
request.messages             # list[InputMessage] — only "message" items, in order
request.user_messages        # list[InputMessage] — role == "user"
```

---

## The response

### What the builders produce

Every builder corresponds to exactly one model in the Responses API. Names below
are the `openai-python` classes (verified against `openai` 2.32.0); the
[API reference](https://developers.openai.com/api/reference/resources/responses/methods/create)
lists the same schemas in snake_case, so `ResponseOutputMessage` is
`response_output_message` there.

| SDK builder call | OpenAI model | lands in |
|---|---|---|
| `response.create_message()` | `ResponseOutputMessage` — `type: "message"` | `Response.output[]` |
| `message.append_text(t)` / `message.create_text_part()` | `ResponseOutputText` — `type: "output_text"` | `ResponseOutputMessage.content[]` |
| `message.append_refusal(r)` | `ResponseOutputRefusal` — `type: "refusal"` | `ResponseOutputMessage.content[]` |
| `message.add_url_citation(...)` | `ResponseOutputText.AnnotationURLCitation` — `type: "url_citation"` | `ResponseOutputText.annotations[]` |
| `message.add_annotation(a)` | any annotation: `AnnotationURLCitation`, `AnnotationFileCitation`, `AnnotationFilePath`, `AnnotationContainerFileCitation` | `ResponseOutputText.annotations[]` |
| `response.create_reasoning()` | `ResponseReasoningItem` — `type: "reasoning"` | `Response.output[]` |
| `reasoning.append_summary(t)` / `reasoning.create_summary_part()` | `ResponseReasoningItem.Summary` — `type: "summary_text"` | `ResponseReasoningItem.summary[]` |
| `reasoning.append_text(t)` | `ResponseReasoningItem.Content` — `type: "reasoning_text"` | `ResponseReasoningItem.content[]` |
| `reasoning.set_encrypted_content(c)` | — | `ResponseReasoningItem.encrypted_content` |
| `response.create_function_call(...)` | `ResponseFunctionToolCall` — `type: "function_call"` | `Response.output[]` |
| `response.create_custom_tool_call(...)` | `ResponseCustomToolCall` — `type: "custom_tool_call"` | `Response.output[]` |
| `response.add_raw_item(d)` | any other `ResponseOutputItem` member — `ResponseFunctionWebSearch`, `ResponseFileSearchToolCall`, `ImageGenerationCall`, `McpCall`, `ResponseCodeInterpreterToolCall`, … | `Response.output[]` |
| `response.set_usage(...)` | `ResponseUsage`, with `InputTokensDetails` / `OutputTokensDetails` | `Response.usage` |
| `response.set_incomplete(reason)` | `Response.IncompleteDetails`, and `Response.status = "incomplete"` | `Response.incomplete_details` |
| `response.set_response_id` / `set_created` / `set_model` | — | `Response.id` / `.created_at` / `.model` |
| a raised `DIALException` | `ResponseError` | `Response.error`, with `Response.status = "failed"` |
| the handler as a whole | `Response` — `object: "response"` | the block response body, and the payload of `response.completed` |

`Response.output[]` is typed as `ResponseOutputItem`, a union discriminated on
`type`. Only the members listed above get a typed builder in this round;
everything else goes through `add_raw_item`, and round 2's DIAL features are
carried as extra fields on these same models rather than as new union members.

Two models in the union have no builder on purpose:
`ResponseFunctionToolCallOutputItem` and `ResponseCustomToolCallOutputItem` are
*inputs* — the client sends them back in `input` after running a tool — so they
appear in the request as `FunctionCallOutputItem` / `CustomToolCallOutputItem`.

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
  on entry and closes on a clean exit.
- Calling `append_*` / `add_*` on an unopened or closed builder raises a
  `runtime_error`, with the same message style as chat completion
  (`"Trying to append text to a closed message"`).
- `await response.aflush()` waits until everything queued so far has been written
  to the socket, unchanged from chat completion.

**Several items may be open at once**, and their deltas may interleave — this is
legal in the protocol, because every delta event carries its own `item_id` and
`output_index`.

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
RAG-style applications should reach for first. Round 2 adds `add_file` to this
builder for returning a payload rather than a reference.

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

The Responses-only free-form tool call, for adapters proxying a model that emits
them:

```python
with response.create_custom_tool_call(name="my_tool") as call:
    call.append_input("free-form text, not JSON")
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

# terminal status
response.set_incomplete(IncompleteReason.MAX_OUTPUT_TOKENS)

# envelope
response.set_response_id("resp_...")
response.set_created(1695298034)
response.set_model("gpt-5-2025-08-07")

# transport
response.append_header("X-My-Header", "value")

# introspection
response.stream          # bool
response.items           # tuple[ItemBuilder, ...] created so far
await response.aflush()
```

Guard rails match chat completion: `set_response_id` / `set_created` /
`set_model` raise once generation has started; `set_usage` raises on a second
call. Unlike chat completion, `set_usage` does **not** require all output to be
finished — the Responses `usage` field lives on the response snapshot, which is
only serialised at the end anyway.

Round 2 adds `set_state`, `set_form_schema`, `add_usage_per_model`,
`set_discarded_input_items` and `set_cache_breakpoint`.

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
| `response.set_usage(...)` | nothing immediately; folded into the terminal snapshot |
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

The alternatives were OpenAI's standalone `event: error`, which leaves the
response without a terminal state, and chat completion's bare
`data: {"error": …}`, which is not a Responses event at all. `response.failed`
keeps the response state machine consistent and preserves the partial `output`.

---

## Worked examples

### 1. A model adapter: reasoning, tool calls, pass-through

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
```

### 2. Text-to-image, inline

```python
class RenderTextApplication(Responses):
    async def responses(self, request: Request, response: Response) -> None:
        text = request.messages[-1].text()
        image_base64 = text_to_image_base64(text)

        with response.create_message() as message:
            message.append_text(
                f"![Image](data:image/png;base64,{image_base64})"
            )
```

Returning the image as a DIAL file instead of an inline data URI is round 2.

---

## Explicitly deferred

Not in this round, so that review can stay focused:

| deferred | to |
|---|---|
| stages | [round 2](./round_2_dial_features.md) |
| files (ex-attachments) on messages and stages | [round 2](./round_2_dial_features.md) |
| `state`, `form_schema`, `form_value`, the `configuration` endpoint | [round 2](./round_2_dial_features.md) |
| `statistics`: `usage_per_model`, `discarded_input_items` | [round 2](./round_2_dial_features.md) |
| `max_prompt_tokens`, `custom_fields`, cache breakpoints | [round 2](./round_2_dial_features.md) |
| chat completion ↔ Responses conversion helpers | [round 3](./round_3_improvements.md) |
| typed builders for built-in tool items (`web_search_call`, …) | [round 3](./round_3_improvements.md) |
| `tokenize` / `truncate_prompt` | [round 3](./round_3_improvements.md) |

Permanently out of scope: `previous_response_id`, `background`, `conversation`,
server-side `store`.
