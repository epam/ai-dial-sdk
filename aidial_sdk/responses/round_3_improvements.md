# Round 3 — possible improvements

> Part of the [Responses API SDK design](./design_draft.md). Optional follow-ups
> to [round 1](./round_1_vanilla_responses.md) and
> [round 2](./round_2_dial_features.md). Nothing here is required for a usable
> SDK, nothing here blocks anything else, and the items are independent — each is
> its own small PR, picked up when there is a reason to.

This file is a parking lot, not a plan. Items are listed roughly by expected
value, with the trigger that would make one worth doing.

---

## Chat completion conversion helpers

Helpers to convert a chat completion request into a Responses request and a
Responses response back into a chat completion response, so an existing DIAL
application can serve both protocols from one implementation.

```python
from aidial_sdk.responses.convert import (
    to_responses_request,      # chat_completion.Request -> responses.Request
    to_chat_completion,        # drive a ChatCompletion impl from a Responses handler
)
```

The conversion is lossy in one direction only: chat completion has no counterpart
for reasoning items, custom tool calls, annotations or per-item statuses. Rounds 1
and 2 are designed to keep the other direction exact — that is why DIAL extensions
are encoded in `custom_content` rather than as new item types
([round 2](./round_2_dial_features.md#the-encoding-rule)).

**Trigger:** the first application that has to serve both endpoints without
duplicating its logic.

## Typed builders for built-in tool items

Round 1 handles `web_search_call`, `file_search_call`, `image_generation_call`,
`code_interpreter_call`, `mcp_call` and friends through `RawItem` on the way in
and `response.add_raw_item()` on the way out. That is correct but untyped, and it
cannot stream — the item is emitted whole.

This item adds real builders for whichever types turn out to matter, with their
streaming events (`response.image_generation_call.partial_image`,
`response.web_search_call.searching`, …).

**Trigger:** an adapter that proxies a model emitting these items and needs to
stream them rather than buffer them.

## Native `POST /v1/responses` route

The SDK registers `POST /openai/deployments/{name}/responses`, matching DIAL's
deployment-based routing. OpenAI's own shape is `POST /v1/responses` with `model`
in the body. If DIAL Core exposes the native shape, the SDK may need to serve it
too — probably as an opt-in flag on `add_responses` that reads the deployment name
from `model`.

**Trigger:** a decision on the Core side. Tracked as an open question in the
[design draft](./design_draft.md#open-questions).

## Stages as a dedicated output item

Round 2 encodes a stage as `custom_content.stages` on the assistant message,
because DIAL extensions should not expand the protocol's item vocabulary. The
alternative — a `{"type": "dial.stage", …}` output item with its own
`response.dial.stage.*` events — is cleaner: exact ordering relative to text,
per-item status, no merge semantics, no lazily-opened carrier message.

The SDK surface (`response.create_stage`) is identical either way, and the wire
mapping lives behind one seam, so this is a change in one module.

**Trigger:** stage ordering relative to text turning out to matter to DIAL Chat,
plus confirmation that the OpenAI clients tolerate unknown `output` item types and
unknown SSE event names.

## Forms as a custom tool call

Round 2 keeps the chat completion encoding (`custom_content.form_schema` /
`custom_content.form_value`). Modelling the round-trip as a `custom_tool_call`
named `dial:forms` plus a `custom_tool_call_output` is more idiomatic for the
Responses API and gives the filled value a natural home.

It requires the client to opt in with
`tools: [{"type": "custom", "name": "dial:forms"}]`, so it is a DIAL Chat change,
not just an SDK change. `set_form_schema` / `request.form_value` stay the only
application-visible API either way.

**Trigger:** DIAL Chat being ready to send the tool declaration.

## `tokenize` / `truncate_prompt` for Responses

Both deployment endpoints take a chat-completion-shaped body today, so they were
left out of round 1. A Responses-shaped variant needs its own protocol work —
`truncate_prompt` in particular has to return indices into `input`, which is a
heterogeneous item list rather than a message list.

**Trigger:** a Responses deployment that needs prompt truncation. Note
`max_prompt_tokens` and `set_discarded_input_items` already cover the common case
from round 2.

## Smaller items

- **`response.set_metadata(...)`** — echo the request's `metadata` back on the
  response, which OpenAI does automatically. Trivial, but needs a decision on
  whether the SDK or Core owns it.
- **`include` handling** — `include: ["reasoning.encrypted_content"]` and friends
  currently reach the application as a raw list. A typed enum plus helpers that
  make the builders honour it would remove a class of adapter bug.
- **`logprobs`** — `top_logprobs` is accepted in round 1 but no builder emits
  logprobs on text parts. Only matters for adapters whose upstream provides them.
