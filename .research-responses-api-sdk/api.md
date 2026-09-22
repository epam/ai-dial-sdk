# DIAL Responses SDK — server-side API sketch

Python pseudo-code. Every line that puts bytes on the wire is annotated with the
event type it produces. Event catalogue and field-level schemas:
[`event.md`](./event.md).

- [Entry point](#entry-point)
- [Conventions](#conventions)
- [Object model](#object-model)
- [Recipes](#recipes) — one minimal snippet per event type
- [Fluent form](#fluent-form)
- [Escape hatches](#escape-hatches)

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
closes that block with `status="incomplete"`, then fails the response:
`error` followed by `response.failed`.

---

## Object model

**Legend**

| Mark | Meaning |
|---|---|
| `(ctx)` | context manager — `with` brackets it and emits its `enter:` / `exit:` events (C2); `.close()` is the non-lexical equivalent (C1) |
| `-> Cls` | returns a child builder |
| `-> self` | fluent mutator, chainable (C4) |
| `# ->` | the event(s) this call puts on the wire |

Every `(ctx)` builder also has `.close()`; every one that is an **output item**
additionally has `.id -> str` (the `item_id` the SDK assigned) and
`.set_incomplete()` (close with `status="incomplete"`). Neither is repeated in
the tree below.

`fail()` exists only on the two MCP builders, because MCP is the only tool family
with failure *events*. Everywhere else a failure is an exception, and C6 turns it
into `error` + `response.failed`.

```
Response (ctx — entered and exited by the framework, never by application code)
│    enter: response.created
│           response.in_progress
│    exit:  response.completed
│
├─ append_text(str) -> self                          # shortcut into a default Message/TextPart
├─ append_refusal(str) -> self                       # shortcut into a default Message/RefusalPart
├─ set_usage(input_tokens, output_tokens, **details) -> self    # no event; final snapshot only
├─ queued() -> self                                  # -> response.queued
├─ set_incomplete(reason) -> self                    # -> response.incomplete   (replaces .completed)
├─ error(code, message, param=None) -> self          # -> error
├─ fail(code, message) -> self                       # -> error
│                                                    #    response.failed
├─ add_item(item | dict) -> None                     # -> response.output_item.added
│                                                    #    response.output_item.done
├─ emit(event) -> None                               # -> that event verbatim (bypasses the accumulator)
│
├─ create_message() -> Message (ctx)
│  │    enter: response.output_item.added            item.type="message"
│  │    exit:  response.output_item.done
│  ├─ set_phase("commentary" | "final_answer") -> self           # no event
│  ├─ append_text(str) -> self                       # shortcut into a default TextPart
│  ├─ append_refusal(str) -> self                    # shortcut into a default RefusalPart
│  │
│  ├─ create_text() -> TextPart (ctx)
│  │  │    enter: response.content_part.added        part.type="output_text"
│  │  │    exit:  response.output_text.done
│  │  │           response.content_part.done
│  │  ├─ append(str) -> self                         # -> response.output_text.delta
│  │  ├─ add_annotation(Annotation) -> self          # -> response.output_text.annotation.added
│  │  └─ add_logprobs([Logprob]) -> self             # no event; rides the next delta
│  │
│  └─ create_refusal() -> RefusalPart (ctx)
│     │    enter: response.content_part.added        part.type="refusal"
│     │    exit:  response.refusal.done
│     │           response.content_part.done
│     └─ append(str) -> self                         # -> response.refusal.delta
│
├─ create_reasoning() -> Reasoning (ctx)
│  │    enter: response.output_item.added            item.type="reasoning"
│  │    exit:  response.output_item.done
│  ├─ set_encrypted_content(str) -> self             # no event; output_item.done only
│  ├─ append_summary(str) -> self                    # shortcut into a default SummaryPart
│  ├─ append_text(str) -> self                       # shortcut into a default ReasoningTextPart
│  │
│  ├─ create_summary() -> SummaryPart (ctx)          # summary[summary_index] — NOT a content part
│  │  │    enter: response.reasoning_summary_part.added
│  │  │    exit:  response.reasoning_summary_text.done
│  │  │           response.reasoning_summary_part.done
│  │  ├─ append(str) -> self                         # -> response.reasoning_summary_text.delta
│  │  └─ set_incomplete() -> self                    # no event; sets part.status on the exit event
│  │
│  └─ create_text() -> ReasoningTextPart (ctx)       # content[content_index]
│     │    enter: response.content_part.added        part.type="reasoning_text"
│     │    exit:  response.reasoning_text.done
│     │           response.content_part.done
│     └─ append(str) -> self                         # -> response.reasoning_text.delta
│
├─ create_function_call(call_id, name) -> FunctionCall (ctx)          # client-side
│  │    enter: response.output_item.added            item.type="function_call"
│  │    exit:  response.function_call_arguments.done
│  │           response.output_item.done
│  ├─ append_arguments(str) -> self                  # -> response.function_call_arguments.delta
│  └─ set_arguments(str | dict) -> self              # -> response.function_call_arguments.delta  (one shot)
│
├─ create_custom_tool_call(call_id, name) -> CustomToolCall (ctx)     # client-side
│  │    enter: response.output_item.added            item.type="custom_tool_call"
│  │    exit:  response.custom_tool_call_input.done
│  │           response.output_item.done
│  ├─ append_input(str) -> self                      # -> response.custom_tool_call_input.delta
│  └─ set_input(str) -> self                         # -> response.custom_tool_call_input.delta  (one shot)
│
├─ create_web_search() -> WebSearch (ctx)                             # server-side
│  │    enter: response.output_item.added            item.type="web_search_call"
│  │           response.web_search_call.in_progress
│  │    exit:  response.web_search_call.completed
│  │           response.output_item.done
│  ├─ searching(query=None) -> self                  # -> response.web_search_call.searching
│  ├─ set_action(Action) -> self                     # no event; output_item.done only
│  └─ add_source(url, ...) -> self                   # no event; output_item.done only
│
├─ create_file_search() -> FileSearch (ctx)                           # server-side
│  │    enter: response.output_item.added            item.type="file_search_call"
│  │           response.file_search_call.in_progress
│  │    exit:  response.file_search_call.completed
│  │           response.output_item.done
│  ├─ searching(queries=[...]) -> self               # -> response.file_search_call.searching
│  └─ add_result(file_id, filename, text, score, attributes=None) -> self   # no event
│
├─ create_image_generation() -> ImageGeneration (ctx)                 # server-side
│  │    enter: response.output_item.added            item.type="image_generation_call"
│  │           response.image_generation_call.in_progress
│  │    exit:  response.image_generation_call.completed
│  │           response.output_item.done
│  ├─ generating() -> self                           # -> response.image_generation_call.generating
│  ├─ append_partial(b64) -> self                    # -> response.image_generation_call.partial_image
│  └─ set_result(b64) -> self                        # no event; output_item.done only
│
├─ create_code_interpreter(container_id) -> CodeInterpreter (ctx)     # server-side
│  │    enter: response.output_item.added            item.type="code_interpreter_call"
│  │           response.code_interpreter_call.in_progress
│  │    exit:  response.code_interpreter_call.completed
│  │           response.output_item.done
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
│  ├─ add_tool(name, input_schema, description=None, annotations=None) -> self   # no event
│  └─ fail(error) -> self                            # no event; switches the exit to .failed
│
├─ create_mcp_call(server_label, name) -> McpCall (ctx)               # server-side
│  │    enter: response.output_item.added            item.type="mcp_call"
│  │           response.mcp_call.in_progress
│  │    exit:  response.mcp_call.completed  — or  response.mcp_call.failed
│  │           response.output_item.done
│  ├─ append_arguments(str) -> self                  # -> response.mcp_call_arguments.delta
│  ├─ set_output(str) -> self                        # -> response.mcp_call_arguments.done   (C3 flush)
│  └─ fail(error) -> self                            # -> response.mcp_call_arguments.done   (C3 flush)
│                                                    #    switches the exit to .failed
│
└─ create_audio() -> Audio (ctx)                     # response-level: no item, no output_index
   │    enter: (no event)
   │    exit:  response.audio.transcript.done
   │           response.audio.done
   ├─ append(bytes | b64) -> self                    # -> response.audio.delta
   └─ append_transcript(str) -> self                 # -> response.audio.transcript.delta
```

Fourteen further output item types have no lifecycle events of their own and go
through `add_item()` — see [Escape hatches](#escape-hatches).

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

## Escape hatches

Fourteen of the 28 output item types have no lifecycle events of their own
(`computer_call`, `local_shell_call`, `apply_patch_call`, `mcp_approval_request`,
`program`, `compaction`, all the `*_output` items, …). They ship whole:

```python
response.add_item(McpApprovalRequest(...))      # -> response.output_item.added
                                                #    response.output_item.done
```

Same door for an item type the SDK does not model yet — pass a dict, the SDK
only supplies `id` and `output_index`:

```python
response.add_item({"type": "some_future_item", "foo": "bar"})
                                                # -> response.output_item.added
                                                #    response.output_item.done
```

And for a raw event the SDK has no builder for, bypassing the accumulator
(`sequence_number` is still assigned):

```python
response.emit(ResponseWebSearchCallSearchingEvent(item_id="...", output_index=0))
```
