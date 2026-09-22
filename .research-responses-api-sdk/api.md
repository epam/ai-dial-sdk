# DIAL Responses SDK — server-side API sketch

Python pseudo-code. Every line that puts bytes on the wire is annotated with the
event type it produces. Event catalogue and field-level schemas:
[`event.md`](./event.md).

- [Entry point](#entry-point)
- [Conventions](#conventions)
- [Object model](#object-model)
- [Recipes](#recipes) — one minimal snippet per event type
- [Fluent form](#fluent-form)
- [One-shot items](#one-shot-items) — the 18 item types with no lifecycle
- [The escape hatch](#the-escape-hatch) — unsafe, raw events only

---

## Entry point

```python
from openai.types.responses import ResponseCreateParams   # the request, re-exported
from aidial_sdk.responses import ResponsesApplication, Request, Response

class MyApp(ResponsesApplication):
    async def create_response(self, request: Request, response: Response) -> None:
        # `Request` is a pydantic mirror of ResponseCreateParams (which is a
        # TypedDict, i.e. not validatable on the server side).
        if request.tools:
            ...
        response.append_text("hi")
```

`response: Response` is the **only** handle the application ever needs.
Everything else is reached through it.

The handler's lifetime *is* the response's lifetime, so the two outermost events
are framework-owned and have no user-facing call:

```python
# before create_response() is awaited      -> response.created
# immediately after                        -> response.in_progress
await app.create_response(request, response)
# on clean return                          -> response.completed
```

---

## Conventions

**C1 — every builder is a context manager *and* has `.close()`.**
`with` is the recommended form; `.close()` exists so builders can outlive a
lexical block (e.g. two interleaved tool calls).

**C2 — entering emits the open event, exiting emits the close event.** That is
the whole reason context managers are the primitive here: the Responses protocol
is strictly bracketed, and `__exit__` runs on the exception path too.

**C3 — delta streams auto-flush.** A `*.done` for a delta stream is emitted by
the *first* of: the owning block exits, an explicit `.close()`, or the next event
on the same item. So you never write `flush()`.

**C4 — mutators return `self`.** Chaining works everywhere (see
[Fluent form](#fluent-form)).

**C5 — the SDK owns all bookkeeping.** `sequence_number`, `output_index`,
`content_index`, `summary_index`, `annotation_index`, item `id`s, per-item
`status`, and the accumulating `Response` snapshot replayed in
`response.created` / `.completed` / `.failed` / `.incomplete`. None of these
appear in application code.

**C6 — exceptions are part of the protocol.** An exception escaping a block
still closes it — the bracket is emitted, so no client is left waiting on a
`.done` that never arrives — and then propagates outward, closing each enclosing
block in turn, until `Response` ends the stream with `error` + `response.failed`.
Each builder's `err:` line in the [object model](#object-model) says exactly what
its unwind emits. Three rules generate all of them:

1. **Delta streams still flush.** A partial `output_text.done` is better than a
   dangling one; the text it restates is the text already sent.
2. **The bad news rides on `status`, not on the event type.** `output_item.done`
   carries `status="incomplete"` (generation stopped) or `"failed"` (it broke).
   `reasoning_summary_part.done` is the one *part*-level event with a `status`
   field, and it gets `"incomplete"` too.
3. **A tool's terminal status event is skipped unless a failure variant exists.**
   MCP has `mcp_call.failed` and `mcp_list_tools.failed`, so those are emitted.
   Web search, file search, image generation and code interpreter have only a
   `.completed` — emitting it for a call that just threw would state the
   opposite of what happened, so it is omitted and `output_item.done` with
   `status="failed"` carries the outcome. That asymmetry is a gap in the
   protocol, not a choice the SDK gets to make well.

---

## Object model

Split into two milestones. **M1** is everything a generative application needs:
the response lifecycle, messages, reasoning, client-side tool calls, and the
three server-side tools whose protocol is a plain status machine. **M2** is the
long tail — the two tools that carry a second delta stream inside the item, and
the items that have no lifecycle at all.

There is deliberately **no generic `add_item(item)`**. Its argument would be the
28-way `ResponseOutputItem` union, so every caller would have to work out which
member to build and which fields that member requires — the exact discrimination
the SDK exists to do for them. One named method per item type, each with the
arguments that item actually needs, or nothing. Before M2 lands, its item types
are reachable only through [`unsafe_emit`](#the-escape-hatch), and that is the
honest signal that they are not supported yet.

**Legend**

| Mark | Meaning |
|---|---|
| `(ctx)` | context manager — `with` brackets it and emits its `enter:` / `exit:` events (C2); `.close()` is the non-lexical equivalent (C1) |
| `-> Cls` | returns a child builder |
| `-> self` | fluent mutator, chainable (C4) |
| `# ->` | the event(s) this call puts on the wire |
| `enter:` / `exit:` | what a `(ctx)` block emits on the normal path |
| `err:` | what it emits instead when an exception leaves the block (C6) |

Every `(ctx)` builder also has `.close()`; every one that is an **output item**
additionally has `.id -> str` (the `item_id` the SDK assigned) and
`.set_incomplete()` (close with `status="incomplete"`). Neither is repeated in
the trees below.

### M1 — streaming core

The whole response lifecycle plus 8 of the 10 item types that have lifecycle
events.

```
Response (ctx — entered and exited by the framework, never by application code)
│    enter: response.created
│           response.in_progress
│    exit:  response.completed
│    err:   error
│           response.failed
│
├─ append_text(str) -> self                          # shortcut into a default Message/TextPart
├─ append_refusal(str) -> self                       # shortcut into a default Message/RefusalPart
├─ set_usage(input_tokens, output_tokens, **details) -> self    # no event; final snapshot only
├─ queued() -> self                                  # -> response.queued
├─ set_incomplete(reason) -> self                    # -> response.incomplete   (replaces .completed)
├─ error(code, message, param=None) -> self          # -> error
├─ fail(code, message) -> self                       # -> error
│                                                    #    response.failed
├─ unsafe_emit(event) -> None                        # THE escape hatch — see below
│
├─ create_message() -> Message (ctx)
│  │    enter: response.output_item.added            item.type="message"
│  │    exit:  response.output_item.done
│  │    err:   response.output_item.done  (item.status="incomplete")
│  ├─ set_phase("commentary" | "final_answer") -> self           # no event
│  ├─ append_text(str) -> self                       # shortcut into a default TextPart
│  ├─ append_refusal(str) -> self                    # shortcut into a default RefusalPart
│  │
│  ├─ create_text() -> TextPart (ctx)
│  │  │    enter: response.content_part.added        part.type="output_text"
│  │  │    exit:  response.output_text.done
│  │  │           response.content_part.done
│  │  │    err:   response.output_text.done  (whatever was appended)
│  │  │           response.content_part.done
│  │  ├─ append(str) -> self                         # -> response.output_text.delta
│  │  ├─ add_annotation(Annotation) -> self          # -> response.output_text.annotation.added
│  │  └─ add_logprobs([Logprob]) -> self             # no event; rides the next delta
│  │
│  └─ create_refusal() -> RefusalPart (ctx)
│     │    enter: response.content_part.added        part.type="refusal"
│     │    exit:  response.refusal.done
│     │           response.content_part.done
│     │    err:   response.refusal.done  (whatever was appended)
│     │           response.content_part.done
│     └─ append(str) -> self                         # -> response.refusal.delta
│
├─ create_reasoning() -> Reasoning (ctx)
│  │    enter: response.output_item.added            item.type="reasoning"
│  │    exit:  response.output_item.done
│  │    err:   response.output_item.done  (item.status="incomplete")
│  ├─ set_encrypted_content(str) -> self             # no event; output_item.done only
│  ├─ append_summary(str) -> self                    # shortcut into a default SummaryPart
│  ├─ append_text(str) -> self                       # shortcut into a default ReasoningTextPart
│  │
│  ├─ create_summary() -> SummaryPart (ctx)          # summary[summary_index] — NOT a content part
│  │  │    enter: response.reasoning_summary_part.added
│  │  │    exit:  response.reasoning_summary_text.done
│  │  │           response.reasoning_summary_part.done
│  │  │    err:   response.reasoning_summary_text.done
│  │  │           response.reasoning_summary_part.done  (status="incomplete")
│  │  ├─ append(str) -> self                         # -> response.reasoning_summary_text.delta
│  │  └─ set_incomplete() -> self                    # no event; sets part.status on the exit event
│  │
│  └─ create_text() -> ReasoningTextPart (ctx)       # content[content_index]
│     │    enter: response.content_part.added        part.type="reasoning_text"
│     │    exit:  response.reasoning_text.done
│     │           response.content_part.done
│     │    err:   response.reasoning_text.done
│     │           response.content_part.done
│     └─ append(str) -> self                         # -> response.reasoning_text.delta
│
├─ create_function_call(call_id, name) -> FunctionCall (ctx)          # client-side
│  │    enter: response.output_item.added            item.type="function_call"
│  │    exit:  response.function_call_arguments.done
│  │           response.output_item.done
│  │    err:   response.function_call_arguments.done  (partial JSON)
│  │           response.output_item.done  (item.status="incomplete")
│  ├─ append_arguments(str) -> self                  # -> response.function_call_arguments.delta
│  └─ set_arguments(str | dict) -> self              # -> response.function_call_arguments.delta  (one shot)
│
├─ create_custom_tool_call(call_id, name) -> CustomToolCall (ctx)     # client-side
│  │    enter: response.output_item.added            item.type="custom_tool_call"
│  │    exit:  response.custom_tool_call_input.done
│  │           response.output_item.done
│  │    err:   response.custom_tool_call_input.done  (partial)
│  │           response.output_item.done  (item.status="incomplete")
│  ├─ append_input(str) -> self                      # -> response.custom_tool_call_input.delta
│  └─ set_input(str) -> self                         # -> response.custom_tool_call_input.delta  (one shot)
│
├─ create_web_search() -> WebSearch (ctx)                             # server-side
│  │    enter: response.output_item.added            item.type="web_search_call"
│  │           response.web_search_call.in_progress
│  │    exit:  response.web_search_call.completed
│  │           response.output_item.done
│  │    err:   response.output_item.done  (item.status="failed")
│  │           …and NOT .completed — there is no web_search_call failure event
│  ├─ searching(query=None) -> self                  # -> response.web_search_call.searching
│  ├─ set_action(Action) -> self                     # no event; output_item.done only
│  └─ add_source(url, ...) -> self                   # no event; output_item.done only
│
├─ create_file_search() -> FileSearch (ctx)                           # server-side
│  │    enter: response.output_item.added            item.type="file_search_call"
│  │           response.file_search_call.in_progress
│  │    exit:  response.file_search_call.completed
│  │           response.output_item.done
│  │    err:   response.output_item.done  (item.status="failed")
│  │           …and NOT .completed — there is no file_search_call failure event
│  ├─ searching(queries=[...]) -> self               # -> response.file_search_call.searching
│  └─ add_result(file_id, filename, text, score, attributes=None) -> self   # no event
│
├─ create_image_generation() -> ImageGeneration (ctx)                 # server-side
│  │    enter: response.output_item.added            item.type="image_generation_call"
│  │           response.image_generation_call.in_progress
│  │    exit:  response.image_generation_call.completed
│  │           response.output_item.done
│  │    err:   response.output_item.done  (item.status="failed")
│  │           …and NOT .completed — there is no image_generation_call failure event
│  ├─ generating() -> self                           # -> response.image_generation_call.generating
│  ├─ append_partial(b64) -> self                    # -> response.image_generation_call.partial_image
│  └─ set_result(b64) -> self                        # no event; output_item.done only
│
└─ create_audio() -> Audio (ctx)                     # response-level: no item, no output_index
   │    enter: (no event)
   │    exit:  response.audio.transcript.done
   │           response.audio.done
   │    err:   response.audio.transcript.done
   │           response.audio.done
   ├─ append(bytes | b64) -> self                    # -> response.audio.delta
   └─ append_transcript(str) -> self                 # -> response.audio.transcript.delta
```

### M2 — sub-streams and one-shots

Code interpreter and MCP are held back together because each carries a *second*
delta stream inside the item (`code`, `arguments`) alongside its status machine
— they are the only place C3's auto-flush rule does real work, and the only tools
with their own failure events. The 18 one-shot items are held back because they
are breadth, not mechanism.

`fail()` exists only on the two MCP builders. Everywhere else a failure is an
exception, and C6 turns it into `error` + `response.failed`.

```
Response
│
├─ create_code_interpreter(container_id) -> CodeInterpreter (ctx)     # server-side
│  │    enter: response.output_item.added            item.type="code_interpreter_call"
│  │           response.code_interpreter_call.in_progress
│  │    exit:  response.code_interpreter_call.completed
│  │           response.output_item.done
│  │    err:   response.code_interpreter_call_code.done  (if the code stream is open)
│  │           response.output_item.done  (item.status="failed")
│  │           …and NOT .completed — there is no code_interpreter_call failure event
│  ├─ append_code(str) -> self                       # -> response.code_interpreter_call_code.delta
│  ├─ interpreting() -> self                         # -> response.code_interpreter_call_code.done   (C3 flush)
│  │                                                 #    response.code_interpreter_call.interpreting
│  ├─ add_log_output(str) -> self                    # no event; output_item.done only
│  └─ add_image_output(url) -> self                  # no event; output_item.done only
│
├─ create_mcp_list_tools(server_label) -> McpListTools (ctx)          # server-side
│  │    enter: response.output_item.added            item.type="mcp_list_tools"
│  │           response.mcp_list_tools.in_progress
│  │    exit:  response.mcp_list_tools.completed  — or  response.mcp_list_tools.failed
│  │           response.output_item.done
│  │    err:   response.mcp_list_tools.failed
│  │           response.output_item.done
│  ├─ add_tool(name, input_schema, description=None, annotations=None) -> self   # no event
│  └─ fail(error) -> self                            # no event; switches the exit to .failed
│
├─ create_mcp_call(server_label, name) -> McpCall (ctx)               # server-side
│  │    enter: response.output_item.added            item.type="mcp_call"
│  │           response.mcp_call.in_progress
│  │    exit:  response.mcp_call.completed  — or  response.mcp_call.failed
│  │           response.output_item.done
│  │    err:   response.mcp_call_arguments.done  (if open)
│  │           response.mcp_call.failed
│  │           response.output_item.done
│  ├─ append_arguments(str) -> self                  # -> response.mcp_call_arguments.delta
│  ├─ set_output(str) -> self                        # -> response.mcp_call_arguments.done   (C3 flush)
│  └─ fail(error) -> self                            # -> response.mcp_call_arguments.done   (C3 flush)
│                                                    #    switches the exit to .failed
│
│
│  ── one-shot items ── no lifecycle events, so no builder and no `with`: each
│     emits response.output_item.added + response.output_item.done back to back
│     and returns the item it sent (read `.id` off it). One method per item
│     type, each taking that item's own fields — never a union argument.
│
│     Call vs. result is not a free choice — see the `caller` rule under
│     [One-shot items] before emitting any *_output item.
│
├─ add_function_call_output(call_id, output) -> Item
├─ add_custom_tool_call_output(call_id, output) -> Item
├─ add_computer_call(call_id, action, pending_safety_checks=None) -> Item
├─ add_computer_call_output(call_id, output, acknowledged_safety_checks=None) -> Item
├─ add_local_shell_call(call_id, action) -> Item
├─ add_local_shell_call_output(output) -> Item
├─ add_shell_call(call_id, action, environment=None) -> Item
├─ add_shell_call_output(call_id, output, max_output_length=None) -> Item
├─ add_apply_patch_call(call_id, operation) -> Item
├─ add_apply_patch_call_output(call_id, output) -> Item
├─ add_mcp_approval_request(server_label, name, arguments) -> Item
├─ add_mcp_approval_response(approval_request_id, approve, reason=None) -> Item
├─ add_program(call_id, code, fingerprint) -> Item
├─ add_program_output(call_id, result) -> Item
├─ add_tool_search_call(call_id, arguments, execution=None) -> Item
├─ add_tool_search_output(call_id, tools, execution=None) -> Item
├─ add_additional_tools(role, tools) -> Item
└─ add_compaction(encrypted_content) -> Item
```

**Return conventions.** `create_*` returns a builder; a stream mutator returns
`self`; `add_*` returns the item it just sent, because a one-shot has nothing to
chain and you usually want its `.id` (`add_mcp_approval_request(...).id` is the
`approval_request_id` the matching response has to quote).

Of the 28 output item types, 10 have lifecycle events and get a `create_*`
builder; the other **18** have none and get an `add_*` one-shot. Between them
they cover the union exhaustively, so nothing the SDK models requires the
escape hatch.

---

# Recipes

## Response lifecycle

```python
response.queued()                       # -> response.queued
                                        #    (only meaningful for background runs;
                                        #     must be called before any output)
```

```python
response.set_usage(input_tokens=120, output_tokens=48)
                                        # no event; lands in the final snapshot
```

```python
response.set_incomplete("max_output_tokens")
                                        # -> response.incomplete   (terminal, replaces .completed)
```

```python
response.error(code="rate_limit_exceeded", message="slow down", param=None)
                                        # -> error                 (stream-level, no snapshot)
```

```python
response.fail(code="server_error", message="upstream exploded")
                                        # -> error
                                        #    response.failed       (terminal)

# equivalently, and preferred — C6 does it for you:
raise DialException(status_code=500, message="upstream exploded")
                                        # -> error
                                        #    response.failed
```

## Message with text

The bread-and-butter path. Three nesting levels, three bracket pairs.

```python
with response.create_message() as message:      # enter: response.output_item.added   (item.type="message")
    with message.create_text() as text:         # enter: response.content_part.added  (part.type="output_text")
        text.append("Hello")                    #     -> response.output_text.delta
        text.append(" world")                   #     -> response.output_text.delta
                                                # exit:  response.output_text.done
                                                #        response.content_part.done
                                                # exit:  response.output_item.done
```

## Text annotations (citations)

```python
with response.create_message() as message:      # enter: response.output_item.added
    with message.create_text() as text:         # enter: response.content_part.added
        text.append("Kyiv is the capital.")     #     -> response.output_text.delta
        text.add_annotation(                    #     -> response.output_text.annotation.added
            UrlCitation(url="https://...", title="Kyiv", start_index=0, end_index=4)
        )
                                                # exit:  response.output_text.done
                                                #        response.content_part.done
                                                # exit:  response.output_item.done
```

## Refusal

```python
with response.create_message() as message:      # enter: response.output_item.added
    with message.create_refusal() as refusal:   # enter: response.content_part.added  (part.type="refusal")
        refusal.append("I can't help with")     #     -> response.refusal.delta
        refusal.append(" that.")                #     -> response.refusal.delta
                                                # exit:  response.refusal.done
                                                #        response.content_part.done
                                                # exit:  response.output_item.done
```

## Reasoning

One item, two independent child streams — `summary[]` and `content[]` — which is
why `Reasoning` has two different `create_*` methods.

```python
with response.create_reasoning() as reasoning:  # enter: response.output_item.added   (item.type="reasoning")

    with reasoning.create_summary() as summary: # enter: response.reasoning_summary_part.added
        summary.append("Checking the map")      #     -> response.reasoning_summary_text.delta
                                                # exit:  response.reasoning_summary_text.done
                                                #        response.reasoning_summary_part.done

    with reasoning.create_text() as thought:    # enter: response.content_part.added  (part.type="reasoning_text")
        thought.append("Ukraine -> Kyiv")       #     -> response.reasoning_text.delta
                                                # exit:  response.reasoning_text.done
                                                #        response.content_part.done

    reasoning.set_encrypted_content("...")      # no event; lands in output_item.done
                                                # exit:  response.output_item.done
```

An interrupted summary sets the `status` field that only this family has:

```python
    with reasoning.create_summary() as summary: # enter: response.reasoning_summary_part.added
        summary.append("Checking the ma")       #     -> response.reasoning_summary_text.delta
        summary.set_incomplete()                # marks part.status="incomplete"
                                                # exit:  response.reasoning_summary_text.done
                                                #        response.reasoning_summary_part.done  (status="incomplete")
```

## Audio

No `item_id`, no `output_index` — a response-level side channel, so it hangs off
`response` rather than off an item. Two streams closed independently.

```python
with response.create_audio() as audio:          # enter: (no event — audio is not an output item)
    audio.append(pcm_chunk)                     #     -> response.audio.delta
    audio.append_transcript("Hello")            #     -> response.audio.transcript.delta
                                                # exit:  response.audio.transcript.done
                                                #        response.audio.done
```

## Client-side tool calls

The item body *is* the delta stream, so there is no nested content-part block —
C3 flushes the arguments when the item block exits.

```python
with response.create_function_call(            # enter: response.output_item.added   (item.type="function_call")
    call_id="call_1", name="get_weather"
) as call:
    call.append_arguments('{"city":')           #     -> response.function_call_arguments.delta
    call.append_arguments(' "Kyiv"}')           #     -> response.function_call_arguments.delta
                                                # exit:  response.function_call_arguments.done
                                                #        response.output_item.done
```

```python
with response.create_custom_tool_call(         # enter: response.output_item.added   (item.type="custom_tool_call")
    call_id="call_2", name="shell"
) as call:
    call.append_input("ls -la /tmp")            #     -> response.custom_tool_call_input.delta
                                                # exit:  response.custom_tool_call_input.done
                                                #        response.output_item.done
```

## Server-side tool: web search

Server-side tool builders emit *two* events on enter: the generic item bracket
and the tool's own `in_progress`.

```python
with response.create_web_search() as search:    # enter: response.output_item.added   (item.type="web_search_call")
                                                #        response.web_search_call.in_progress
    search.searching(query="dial sdk")          #     -> response.web_search_call.searching
    search.add_source(url="https://...")        # no event; lands in output_item.done
                                                # exit:  response.web_search_call.completed
                                                #        response.output_item.done
```

## Server-side tool: file search

```python
with response.create_file_search() as search:   # enter: response.output_item.added   (item.type="file_search_call")
                                                #        response.file_search_call.in_progress
    search.searching(queries=["dial sdk"])      #     -> response.file_search_call.searching
    search.add_result(file_id="f_1",            # no event; lands in output_item.done
                      filename="readme.md",
                      text="...", score=0.93)
                                                # exit:  response.file_search_call.completed
                                                #        response.output_item.done
```

## Server-side tool: image generation

```python
with response.create_image_generation() as img: # enter: response.output_item.added   (item.type="image_generation_call")
                                                #        response.image_generation_call.in_progress
    img.generating()                            #     -> response.image_generation_call.generating
    img.append_partial(b64_preview_0)           #     -> response.image_generation_call.partial_image (index 0)
    img.append_partial(b64_preview_1)           #     -> response.image_generation_call.partial_image (index 1)
    img.set_result(b64_final)                   # no event; lands in output_item.done
                                                # exit:  response.image_generation_call.completed
                                                #        response.output_item.done
```

## Server-side tool: code interpreter

Two phases in one item: write the code, then run it. `interpreting()` is the
phase switch, and by C3 it flushes the code stream first.

```python
with response.create_code_interpreter(         # enter: response.output_item.added   (item.type="code_interpreter_call")
    container_id="cnt_1"                        #        response.code_interpreter_call.in_progress
) as ci:
    ci.append_code("print(")                    #     -> response.code_interpreter_call_code.delta
    ci.append_code("1 + 1)")                    #     -> response.code_interpreter_call_code.delta
    ci.interpreting()                           #     -> response.code_interpreter_call_code.done   (C3 flush)
                                                #        response.code_interpreter_call.interpreting
    ci.add_log_output("2")                      # no event; lands in output_item.done
                                                # exit:  response.code_interpreter_call.completed
                                                #        response.output_item.done
```

## Server-side tool: MCP tool listing

```python
with response.create_mcp_list_tools(           # enter: response.output_item.added   (item.type="mcp_list_tools")
    server_label="github"                       #        response.mcp_list_tools.in_progress
) as listing:
    listing.add_tool(name="create_issue",       # no event; lands in output_item.done
                     input_schema={...})
                                                # exit:  response.mcp_list_tools.completed
                                                #        response.output_item.done
```

```python
with response.create_mcp_list_tools(           # enter: response.output_item.added
    server_label="github"                       #        response.mcp_list_tools.in_progress
) as listing:
    listing.fail("connection refused")          # no event; arms the failure exit
                                                # exit:  response.mcp_list_tools.failed
                                                #        response.output_item.done
```

## Server-side tool: MCP call

```python
with response.create_mcp_call(                 # enter: response.output_item.added   (item.type="mcp_call")
    server_label="github", name="create_issue"  #        response.mcp_call.in_progress
) as call:
    call.append_arguments('{"title": "bug"}')   #     -> response.mcp_call_arguments.delta
    call.set_output("#42")                      #     -> response.mcp_call_arguments.done   (C3 flush)
                                                # exit:  response.mcp_call.completed
                                                #        response.output_item.done
```

```python
with response.create_mcp_call(                 # enter: response.output_item.added
    server_label="github", name="create_issue"  #        response.mcp_call.in_progress
) as call:
    call.append_arguments('{"title": "bug"}')   #     -> response.mcp_call_arguments.delta
    call.fail("upstream 503")                   #     -> response.mcp_call_arguments.done   (C3 flush)
                                                # exit:  response.mcp_call.failed
                                                #        response.output_item.done
```

---

## Fluent form

C1 + C4 mean the same tree can be written without `with` when there is nothing
to interleave. Identical event sequence to the [message recipe](#message-with-text):

```python
(response
    .create_message()                           # -> response.output_item.added
    .create_text()                              # -> response.content_part.added
    .append("Hello")                            # -> response.output_text.delta
    .append(" world")                           # -> response.output_text.delta
    .close())                                   # -> response.output_text.done
                                                #    response.content_part.done
                                                #    response.output_item.done
```

`close()` on a child closes its unclosed ancestors, which is what makes the chain
terminate cleanly. And the degenerate case stays one line:

```python
response.append_text("Hello world")             # -> response.output_item.added
                                                #    response.content_part.added
                                                #    response.output_text.delta
                                                #    (closed when the handler returns)
```

Two tool calls in flight at once is the case `with` cannot express, and the
reason `.close()` is public:

```python
a = response.create_function_call(call_id="a", name="f")   # -> response.output_item.added
b = response.create_function_call(call_id="b", name="g")   # -> response.output_item.added
a.append_arguments('{"x":')                                # -> response.function_call_arguments.delta
b.append_arguments('{"y":')                                # -> response.function_call_arguments.delta
a.append_arguments(' 1}').close()                          # -> response.function_call_arguments.delta
                                                           #    response.function_call_arguments.done
                                                           #    response.output_item.done
b.append_arguments(' 2}').close()                          # -> ... same three for item b
```

---

## One-shot items

Eighteen of the 28 output item types have no lifecycle events — nothing streams,
so there is nothing to bracket. Each gets a named `add_*` method that emits the
`output_item.added` / `.done` pair back to back and returns the item.

```python
response.add_function_call_output(          # -> response.output_item.added
    call_id="call_1", output="18C, clear"   #    response.output_item.done
)
```

```python
req = response.add_mcp_approval_request(    # -> response.output_item.added
    server_label="github",                  #    response.output_item.done
    name="create_issue",
    arguments='{"title": "bug"}',
)
response.add_mcp_approval_response(         # -> response.output_item.added
    approval_request_id=req.id, approve=True    # response.output_item.done
)
```

The full set, grouped the way the wire groups them:

| Calls | Results |
|---|---|
| `add_computer_call` | `add_computer_call_output` |
| `add_local_shell_call` | `add_local_shell_call_output` |
| `add_shell_call` | `add_shell_call_output` |
| `add_apply_patch_call` | `add_apply_patch_call_output` |
| `add_program` | `add_program_output` |
| `add_tool_search_call` | `add_tool_search_output` |
| `add_mcp_approval_request` | `add_mcp_approval_response` |
| — | `add_function_call_output` |
| — | `add_custom_tool_call_output` |
| `add_additional_tools`, `add_compaction` | — |

There is no generic `add_item(item)` to fall back on, by design: its argument
would be the 28-way `ResponseOutputItem` union, pushing the discrimination work
back onto the caller. An item type this SDK version does not model has no safe
method, and reaching it means the [escape hatch](#the-escape-hatch) — which is
the point, because the SDK cannot track what it cannot type.

---

## The escape hatch

One method, and it is **unsafe**:

```python
response.unsafe_emit(event)
```

It writes a raw event to the wire with only `sequence_number` filled in. It
bypasses everything in C5 — the accumulator does not see it, so the item never
appears in `response.output[]`, `output_index` / `content_index` are yours to get
right, and the `response.completed` snapshot will silently disagree with the
stream a client just consumed. Ordering invariants are not checked either: you
can emit a `.done` for a part that was never opened.

It exists for exactly two cases:

1. **An event type newer than this SDK version.** Construct it as a dict.
2. **A sequence the builders cannot express** — a provider that interleaves
   events in an order the bracketing model forbids, most often when a DIAL
   adapter is proxying an upstream Responses stream verbatim.

```python
# case 2: forwarding an upstream stream untouched
async for upstream_event in client.responses.create(**request.model_dump(), stream=True):
    response.unsafe_emit(upstream_event)    # -> that event verbatim
```

If you reach for it for anything else, the thing you want is missing from the
[object model](#object-model) — that is a bug in the SDK, not a reason to bypass it.
