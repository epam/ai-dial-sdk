# DIAL Responses API SDK — API design draft

> Status: **design proposal, not implemented**.
> This file holds what spans all three delivery rounds: the goals, the mental
> model, the public surface and the migration map. The per-round API surface lives
> in the round documents linked from [Delivery plan](#delivery-plan).

- [Goals](#goals)
- [Mental model](#mental-model)
- [Delivery plan](#delivery-plan)
- [Public surface](#public-surface)
- [Migration cheat sheet](#migration-cheat-sheet)
- [Open questions](#open-questions)

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

**Out of scope by design, not deferred.** DIAL applications and model adapters
are stateless, so the server-side conversation features of the Responses API —
`previous_response_id`, `background`, `conversation` and `store` — are not
supported and are not expected to be. The SDK rejects them rather than accepting
them and behaving differently than the client asked.

Deferred, not rejected: the `/tokenize` and `/truncate_prompt` deployment
endpoints, whose request bodies are chat-completion shaped — parked in
[round 3](./round_3_improvements.md#tokenize--truncate_prompt-for-responses).

---

## Mental model

The single structural difference from chat completion is that **there are no
choices**. A chat completion response is `n` parallel choices, each of which
accumulates content, stages, attachments and tool calls. A Responses response is
**one ordered list of output items**, and everything — the assistant message, each
stage, each tool call, the reasoning — *is* an item in that list.

So `Choice` disappears and `Response` itself becomes the container:

| chat completion | responses | round |
|---|---|:-:|
| `response.create_single_choice()` → `Choice` | `Response` is the container; no intermediate object |
| `choice.append_content(str)` | `message.append_text(str)` on a message item |
| `choice.create_stage(name)` | `response.create_stage(name)` | 2 |
| `choice.add_attachment(...)` | `message.add_file(...)` / `stage.add_file(...)` |
| `choice.set_state(dict)` | `response.set_state(dict)` |
| `choice.set_form_schema(dict)` | `response.set_form_schema(dict)` |
| `choice.create_function_tool_call(...)` | `response.create_function_call(...)` |
| `choice.close(finish_reason)` | per-item `close()`; response status is derived |
| `response.set_usage(prompt_tokens, completion_tokens)` | `response.set_usage(input_tokens, output_tokens)` | 1 |

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

## Delivery plan

The design is split across three PRs so that no single review is thousands of
lines. Each round is a complete, shippable increment.

| round | scope | document |
|---|---|---|
| 1 | The vanilla Responses API: the `Responses` ABC, `add_responses`, the request model, every output item type the protocol defines, streaming and block responses, errors. A round-1 payload contains no DIAL extensions at all. | [round_1_vanilla_responses.md](./round_1_vanilla_responses.md) |
| 2 | DIAL-specific features, all additive: stages, files, state, forms, `statistics`, `max_prompt_tokens`, cache breakpoints, the `configuration` endpoint. | [round_2_dial_features.md](./round_2_dial_features.md) |
| 3 | Optional follow-ups, independent of each other: chat completion conversion helpers, typed builders for built-in tool items, the native `/v1/responses` route, and two encoding decisions worth revisiting. | [round_3_improvements.md](./round_3_improvements.md) |

The split is possible because of the encoding rule adopted in round 2 — DIAL
extensions live inside the objects the vanilla protocol already defines, never as
new output item types — which means round 2 adds methods and fields but changes
nothing round 1 established.

Sequencing and implementation notes:
[implementation_draft.md](./implementation_draft.md).

---

## Public surface

`aidial_sdk.responses` mirrors the layout of `aidial_sdk.chat_completion`.
Names marked **(2)** arrive in round 2; everything else is round 1.

```python
from aidial_sdk.responses import (
    # entry points
    Responses,              # the abstract application class
    Request,                # the parsed request (pydantic)
    Response,               # the response builder

    # output item builders (returned by Response factory methods)
    Message,
    Reasoning,
    FunctionCall,
    CustomToolCall,
    TextPart,
    Stage,                  # (2)

    # enums
    ItemStatus,             # in_progress | completed | incomplete
    ResponseStatus,         # completed | incomplete | failed
    IncompleteReason,       # max_output_tokens | content_filter
    Status,                 # (2) stage status: completed | failed (same as chat_completion)

    # request models
    InputMessage,           # note: Message is the *output* builder
    InputTextPart, InputImagePart, InputFilePart, InputAudioPart,
    OutputTextPart, RefusalPart,
    FunctionCallItem, FunctionCallOutputItem,
    CustomToolCallItem, CustomToolCallOutputItem,
    ReasoningItem, ItemReference, RawItem,
    Tool, FunctionTool, CustomTool, ToolChoice,
    TextConfig, ReasoningConfig,
    Annotation, UrlCitation, FileCitation,

    File,                   # (2)
    CustomContent,          # (2)
    RequestCustomFields,    # (2)
    CacheBreakpoint,        # (2)
    CacheBreakpointPath,    # (2) shared with chat completion
)
```

> Naming collision to be aware of: `Message` is the **output builder**, while the
> request-side model is `InputMessage`. `request.messages` returns
> `list[InputMessage]`. The alternative (`OutputMessage` for the builder) was
> rejected because the builder is what applications type most often, and in
> `chat_completion` the short name likewise belongs to the builder (`Stage` vs
> `RequestStage`).

Round 2 also moves forms to a protocol-neutral module, re-exported from both
packages:

```python
from aidial_sdk.forms import Button, form, FormMetaclass     # new canonical location
from aidial_sdk.chat_completion import Button, FormMetaclass # kept as alias
from aidial_sdk.responses import Button, form, FormMetaclass # re-export
```

---

## Migration cheat sheet

| chat completion | responses | round |
|---|---|:-:|
| `from aidial_sdk.chat_completion import ChatCompletion, Request, Response` | `from aidial_sdk.responses import Responses, Request, Response` | 1 |
| `async def chat_completion(self, request, response)` | `async def responses(self, request, response)` | 1 |
| `app.add_chat_completion(name, impl)` | `app.add_responses(name, impl)` | 1 |
| `request.messages` | `request.messages` (only `message` items) / `request.input_items` (everything) | 1 |
| `message.text()` raises on part lists | `message.text()` concatenates text parts | 1 |
| `message.custom_content.attachments` | `message.files()` | 2 |
| `request.custom_fields.configuration` | `request.configuration` | 2 |
| dig out `custom_content.state` by hand | `request.state` | 2 |
| dig out `custom_content.form_value` by hand | `request.form_value` | 2 |
| `with response.create_single_choice() as choice:` | `with response.create_message() as message:` | 1 |
| `choice.append_content(t)` | `message.append_text(t)` | 1 |
| `choice.content_stream` | `message.content_stream` | 1 |
| `choice.add_attachment(type=…, title=…, data=…, url=…)` | `message.add_file(file_type=…, filename=…, file_data=…, file_url=…)` | 2 |
| — | `message.add_url_citation(url=…, title=…)` | 1 |
| `choice.create_stage(name)` | `response.create_stage(name)` | 2 |
| `stage.append_content` / `append_name` / `add_attachment` | `stage.append_content` / `append_name` / `add_file` | 2 |
| `choice.set_state` / `set_form_schema` | `response.set_state` / `set_form_schema` | 2 |
| `choice.create_function_tool_call(id, name, args)` | `response.create_function_call(name, call_id=…, arguments=…)` | 1 |
| `choice.create_function_call(name, args)` (legacy) | — (dropped; Responses has no `function_call` field) | 1 |
| `choice.close(FinishReason.LENGTH)` | `response.set_incomplete(IncompleteReason.MAX_OUTPUT_TOKENS)` | 1 |
| `FinishReason.TOOL_CALLS` | implied by a `function_call` item in `output` | 1 |
| `response.set_usage(prompt_tokens, completion_tokens)` | `response.set_usage(input_tokens, output_tokens)` | 1 |
| `response.add_usage_per_model(model, prompt_tokens, completion_tokens)` | `response.add_usage_per_model(model, input_tokens, output_tokens)` | 2 |
| `response.set_discarded_messages([…])` | `response.set_discarded_input_items([…])` | 2 |
| `CacheBreakpointPath.messages(i)` | `CacheBreakpointPath.input_items(i)` | 2 |
| `n > 1` | not applicable — no choices | 1 |
| `tokenize` / `truncate_prompt` endpoints | [round 3 candidate](./round_3_improvements.md#tokenize--truncate_prompt-for-responses) | 3 |

---

## Open questions

None of these block the SDK surface; they need a decision before or during
implementation.

- **Endpoint shape.** `POST /openai/deployments/{name}/responses` is what the SDK
  registers. Does Core also expose the OpenAI-native `POST /v1/responses` with
  `model` in the body, and if so does the SDK need to serve it?
- **Handler name.** `responses` (chosen here, matches `chat_completion` /
  `embeddings`) vs `create_response` (reads better in isolation).
- **`discarded_input_items` vs `discarded_messages`** as the `statistics` field
  name. The indices point into `input`, so the former is proposed.
- **`file_type`.** Redundant when `file_data` is a data URI, needed alongside
  `file_url`. Keep it, or require the type to be carried by the URL?
- **`tokenize` / `truncate_prompt`.** Whether a Responses-shaped variant is worth
  specifying at all — `truncate_prompt` would have to return indices into a
  heterogeneous `input` list. Parked in
  [round 3](./round_3_improvements.md#tokenize--truncate_prompt-for-responses).
