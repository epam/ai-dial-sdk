# Round 2 — DIAL-specific features

> Part of the [Responses API SDK design](./design_draft.md). Builds on
> [round 1](./round_1_vanilla_responses.md), which must land first. Everything
> here is additive: no round-1 API changes, only new methods and new fields.

- [Scope](#scope)
- [The encoding rule](#the-encoding-rule)
- [Request extensions](#request-extensions)
- [Files](#files)
- [Stage item](#stage-item)
- [State and forms](#state-and-forms)
- [Statistics](#statistics)
- [Wire additions](#wire-additions)
- [Worked examples](#worked-examples)
- [Verification](#verification)

---

## Scope

Everything a DIAL application needs beyond the vanilla protocol, all of it already
familiar from `aidial_sdk.chat_completion`:

| feature | chat completion today | this round |
|---|---|---|
| stages | `choice.create_stage(name)` | `response.create_stage(name)` |
| files (ex-attachments) | `choice.add_attachment(...)` | `message.add_file(...)`, `stage.add_file(...)` |
| state | `choice.set_state(dict)` | `response.set_state(dict)` |
| form schema | `choice.set_form_schema(dict)` | `response.set_form_schema(dict)` |
| form value | dug out of `custom_content` by hand | `request.form_value` |
| configuration | `custom_fields.configuration` | `request.configuration`, the `configuration` endpoint |
| per-model usage | `response.add_usage_per_model(...)` | `response.add_usage_per_model(...)` |
| discarded history | `response.set_discarded_messages([...])` | `response.set_discarded_input_items([...])` |
| cache breakpoints | `response.set_cache_breakpoint(...)` | same, plus `CacheBreakpointPath.input_items(i)` |
| prompt truncation | `max_prompt_tokens` | `max_prompt_tokens` |

---

## The encoding rule

One rule settles how all of the above appears on the wire: **DIAL-specific
extensions live inside the objects the vanilla protocol already defines, and never
introduce new output item types.**

A client that knows nothing about DIAL must see an ordinary Responses payload.
Extra fields on known objects are ignored by such a client, whereas an unknown
item type in `output` is something it has to cope with. The rule also keeps the
mental model small for application authors: `output` holds the same item types
OpenAI documents, and DIAL's additions hang off them.

Concretely, everything in this round lands in `custom_content` of the assistant
message's `output_text` content part — `ResponseOutputText` in OpenAI's model
names, see [what the builders produce](./round_1_vanilla_responses.md#what-the-builders-produce)
— which is also what chat-completion conversion needs, with one deliberate
exception, `statistics`.

### 1. Stages live inside the message item

A stage is `custom_content.stages` on the assistant message's `output_text`
content part, streamed as `response.output_text.delta` events carrying an empty
`delta` and a `custom_content` payload:

```
event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":6,"item_id":"msg_1","output_index":0,"content_index":0,"delta":"","custom_content":{"stages":[{"index":0,"name":"Downloading"}]}}

```

Consequences the SDK absorbs: stage entries are identified by `index` and merged
by the client, and `response.create_stage()` called before any text opens the
carrier message item that the stages hang off, keeping it open until the response
ends.

The rejected alternative was a dedicated `{"type": "dial.stage", …}` output item
with its own `response.dial.stage.*` events. It is cleaner in isolation — exact
ordering relative to text, per-item status, no merge semantics — but it violates
the rule above: it expands the protocol's item vocabulary, and it asks everyone
writing or reading DIAL responses to learn a shape that is not in the Responses
API. It also maps less directly onto `choice.custom_content.stages` for
chat-completion conversion. Worth revisiting only if stage ordering relative to
text turns out to matter to DIAL Chat
([round 3](./round_3_improvements.md#stages-as-a-dedicated-output-item)).

### 2. Other DIAL extensions follow the same rule

`state`, `form_schema` and `files` live in `custom_content` of the assistant
message's `output_text` part. The SDK still exposes them per response
(`response.set_state`), because in Responses there is nothing per-choice to hang
them on.

`statistics` (`usage_per_model`, `discarded_input_items`) is the one exception:
it stays a top-level field of the response object, as it is in DIAL chat
completion. It is a response-level concern with no sensible per-item home, DIAL
Core already reads it from the top level, and it is additive — a vanilla client
ignores it.

### 3. Forms in `custom_content`, not a custom tool call

The schema travels as `custom_content.form_schema` on the assistant message and
the filled value as `custom_content.form_value` on the user message — the chat
completion encoding, unchanged.

Modelling forms as a `custom_tool_call` named `dial:forms` was the attractive
alternative: the round-trip becomes a first-class pair of items and the filled
value gets a natural home in `custom_tool_call_output`. It loses on the same rule
as decision 1, and it additionally requires the client to opt in by sending
`tools: [{"type": "custom", "name": "dial:forms"}]`, which is a behaviour change
for DIAL Chat for no application-visible gain
([round 3](./round_3_improvements.md#forms-as-a-custom-tool-call)).

---

## Request extensions

Added to the round-1 request model:

```python
class ResponsesRequest(...):
    # --- DIAL extensions ---
    max_prompt_tokens: PositiveInt | None = None
    custom_fields: RequestCustomFields | None = None   # configuration, cache_breakpoint
```

Added to `InputMessage`:

```python
class InputMessage(...):
    custom_content: CustomContent | None = None
    custom_fields: MessageCustomFields | None = None   # cache_breakpoint

    def files(self) -> list[File]: ...
```

```python
class CustomContent(ExtraAllowModel):
    stages: list[Stage] | None = None
    files: list[File] | None = None
    state: dict | None = None
    form_value: Any | None = None
    form_schema: Any | None = None
```

### Navigation helpers

Added to the round-1 set, these are the accessors every application would
otherwise write by hand — `examples/tic_tac_toe/app/request.py` is exactly this
boilerplate today:

```python
request.state                # dict | None  — custom_content.state of the last assistant message
request.form_value           # Any  | None  — the form value submitted by the user
request.configuration        # dict | None  — custom_fields.configuration
```

`request.form_value` and `request.state` deliberately hide *where* those values
live on the wire: whether a filled form arrives as `custom_content.form_value` on
the last user message or as a `custom_tool_call_output` item is an adapter
concern, not an application concern. That keeps
[round 3](./round_3_improvements.md#forms-as-a-custom-tool-call) free to change
the encoding without touching applications.

---

## Files

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
native `input_file` / `input_image` content parts, and `custom_content.files` of
assistant messages echoed back from history.

On the response side, `add_file` is added to both `Message` and `Stage` as an
overload set, like `choice.add_attachment` today — pass a `File`, or pass its
fields as keywords:

```python
    @overload
    def add_file(self, file: File) -> None: ...
    @overload
    def add_file(
        self, *, filename: str | None = None, file_data: str | None = None,
        file_url: str | None = None, file_type: str | None = None,
        reference_url: str | None = None, reference_type: str | None = None,
    ) -> None: ...
```

`add_file` is how you return a payload — an image, a generated document, a
markdown snippet. For a reference, prefer round 1's `add_url_citation`, which is
protocol-native.

---

## Stage item

The DIAL stage keeps its chat completion API verbatim — only its owner changes
from `Choice` to `Response`:

```python
stage = response.create_stage(name=None)


class Stage:
    def append_name(self, name: str) -> None: ...
    def append_content(self, content: str) -> None: ...
    @property
    def content_stream(self) -> ContentStream: ...
    def add_file(self, ...) -> None: ...          # same overload set as Message.add_file
    def open(self) -> None: ...
    def close(self, status: Status = Status.COMPLETED) -> None: ...
```

```python
with response.create_stage("Downloading the document") as stage:
    documents = loader.load()
    stage.append_content(f"Loaded {len(documents)} pages")
```

`Stage` closes with `Status.FAILED` when the block exits with an exception, which
is what `chat_completion.Stage.__exit__` does today.

Stages and the answer may be open at the same time, which is what round 1's
"several items may be open at once" invariant buys:

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

---

## State and forms

```python
response.set_state({"board": ...})
response.set_form_schema(MyForm.model_json_schema())
```

Both raise on a second call, matching the chat completion guard rails.

The form *definition* side is unchanged — `Button`, the `form` decorator and
`FormMetaclass` are protocol-neutral and simply move to a new
`aidial_sdk.forms` module, re-exported from both packages so nothing breaks:

```python
from aidial_sdk.forms import Button, form, FormMetaclass     # new canonical location
from aidial_sdk.chat_completion import Button, FormMetaclass # kept as alias
from aidial_sdk.responses import Button, form, FormMetaclass # re-export
```

The DIAL-specific plumbing stays behind two calls:

```python
# server -> client: publish the schema the user should fill in
response.set_form_schema(MoveForm.model_json_schema())

# client -> server: read back what the user submitted
if form_value := request.form_value:
    move = MoveForm.model_validate(form_value)
```

This round also adds the `configuration` endpoint to the `Responses` ABC, since a
configuration schema is what drives the initial form:

```python
class Responses(ABC):
    ...
    async def configuration(
        self, request: ConfigurationRequest
    ) -> ConfigurationResponse | dict: ...
```

`add_responses` registers `GET /openai/deployments/{name}/configuration` when
`configuration` is overridden, exactly as `add_chat_completion` does.

---

## Statistics

```python
response.add_usage_per_model("gpt-5", input_tokens=120, output_tokens=42)
response.set_discarded_input_items([0, 1, 2])   # was: set_discarded_messages
```

Both land in the top-level `statistics` object, as in chat completion.
`set_discarded_input_items` raises on a second call.

`set_cache_breakpoint` carries over unchanged, and `CacheBreakpointPath` gains
`input_items(idx)` (`prefix.body.input[{idx}]`) alongside the existing
`messages(idx)` and `tools(idx)`:

```python
response.set_cache_breakpoint(
    cache_breakpoint_path=CacheBreakpointPath.input_items(3),
    cache_expire_at=...,
    cache_metadata=...,
)
```

---

## Wire additions

Added to the round-1 event table:

| SDK call | emitted events (streaming) |
|---|---|
| `response.create_stage(name)` / `stage.open()` | `response.output_text.delta` with empty `delta` + `custom_content.stages[i].name` |
| `stage.append_content(c)` | `response.output_text.delta` with empty `delta` + `custom_content.stages[i].content` |
| `stage.append_name(n)` | `response.output_text.delta` with empty `delta` + `custom_content.stages[i].name` |
| `stage.add_file(...)` | `response.output_text.delta` with empty `delta` + `custom_content.stages[i].files` |
| `stage.close(status)` | `response.output_text.delta` with empty `delta` + `custom_content.stages[i].status` |
| `message.add_file(...)` | `response.output_text.delta` with empty `delta` + `custom_content.files` |
| `response.set_state(...)` / `set_form_schema(...)` | nothing immediately; folded into the terminal snapshot |
| `response.add_usage_per_model(...)` / `set_discarded_input_items(...)` | nothing immediately; folded into the terminal snapshot |

The terminal `response.completed` snapshot carries the merged `custom_content` on
the message's `output_text` part, plus top-level `statistics`.

---

## Worked examples

### 1. RAG with stages, citations and files

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

            # Protocol-native citations (round 1)
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

Note how much request-side boilerplate the navigation helpers remove.

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

---

## Verification

Beyond the per-feature unit tests, two checks are specific to this round:

- **Round-1 payloads are unchanged.** An application that uses no DIAL feature
  must produce byte-identical output to round 1 — no empty `custom_content`, no
  empty `statistics`.
- **Chat-completion equivalence.** For each ported example, the DIAL extensions in
  the Responses payload must carry the same values as the chat completion payload
  from the same inputs. This is the property that makes conversion between the two
  protocols possible later
  ([round 3](./round_3_improvements.md#chat-completion-conversion-helpers)).
