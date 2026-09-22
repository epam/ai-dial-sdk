# Responses API — server event catalogue

- [Responses API — server event catalogue](#responses-api--server-event-catalogue)
  - [Addressing model](#addressing-model)
  - [Summary table](#summary-table)
- [Response lifecycle](#response-lifecycle)
  - [response.created](#responsecreated)
  - [response.in\_progress](#responsein_progress)
  - [response.queued](#responsequeued)
  - [response.completed](#responsecompleted)
  - [response.incomplete](#responseincomplete)
  - [response.failed](#responsefailed)
  - [error](#error)
- [Output item lifecycle](#output-item-lifecycle)
  - [response.output\_item.added](#responseoutput_itemadded)
  - [response.output\_item.done](#responseoutput_itemdone)
- [Content part lifecycle](#content-part-lifecycle)
  - [response.content\_part.added](#responsecontent_partadded)
  - [response.content\_part.done](#responsecontent_partdone)
- [Assistant text](#assistant-text)
  - [response.output\_text.delta](#responseoutput_textdelta)
  - [response.output\_text.done](#responseoutput_textdone)
  - [response.output\_text.annotation.added](#responseoutput_textannotationadded)
- [Refusal](#refusal)
  - [response.refusal.delta](#responserefusaldelta)
  - [response.refusal.done](#responserefusaldone)
- [Reasoning — summary](#reasoning--summary)
  - [response.reasoning\_summary\_part.added](#responsereasoning_summary_partadded)
  - [response.reasoning\_summary\_text.delta](#responsereasoning_summary_textdelta)
  - [response.reasoning\_summary\_text.done](#responsereasoning_summary_textdone)
  - [response.reasoning\_summary\_part.done](#responsereasoning_summary_partdone)
- [Reasoning — text](#reasoning--text)
  - [response.reasoning\_text.delta](#responsereasoning_textdelta)
  - [response.reasoning\_text.done](#responsereasoning_textdone)
- [Audio](#audio)
  - [response.audio.delta](#responseaudiodelta)
  - [response.audio.done](#responseaudiodone)
  - [response.audio.transcript.delta](#responseaudiotranscriptdelta)
  - [response.audio.transcript.done](#responseaudiotranscriptdone)
- [Client-side tool calls](#client-side-tool-calls)
  - [response.function\_call\_arguments.delta](#responsefunction_call_argumentsdelta)
  - [response.function\_call\_arguments.done](#responsefunction_call_argumentsdone)
  - [response.custom\_tool\_call\_input.delta](#responsecustom_tool_call_inputdelta)
  - [response.custom\_tool\_call\_input.done](#responsecustom_tool_call_inputdone)
- [Server-side tools](#server-side-tools)
  - [Web search](#web-search)
    - [response.web\_search\_call.in\_progress](#responseweb_search_callin_progress)
    - [response.web\_search\_call.searching](#responseweb_search_callsearching)
    - [response.web\_search\_call.completed](#responseweb_search_callcompleted)
  - [File search](#file-search)
    - [response.file\_search\_call.in\_progress](#responsefile_search_callin_progress)
    - [response.file\_search\_call.searching](#responsefile_search_callsearching)
    - [response.file\_search\_call.completed](#responsefile_search_callcompleted)
  - [Image generation](#image-generation)
    - [response.image\_generation\_call.in\_progress](#responseimage_generation_callin_progress)
    - [response.image\_generation\_call.generating](#responseimage_generation_callgenerating)
    - [response.image\_generation\_call.partial\_image](#responseimage_generation_callpartial_image)
    - [response.image\_generation\_call.completed](#responseimage_generation_callcompleted)
  - [Code interpreter](#code-interpreter)
    - [response.code\_interpreter\_call.in\_progress](#responsecode_interpreter_callin_progress)
    - [response.code\_interpreter\_call\_code.delta](#responsecode_interpreter_call_codedelta)
    - [response.code\_interpreter\_call\_code.done](#responsecode_interpreter_call_codedone)
    - [response.code\_interpreter\_call.interpreting](#responsecode_interpreter_callinterpreting)
    - [response.code\_interpreter\_call.completed](#responsecode_interpreter_callcompleted)
  - [MCP — tool listing](#mcp--tool-listing)
    - [response.mcp\_list\_tools.in\_progress](#responsemcp_list_toolsin_progress)
    - [response.mcp\_list\_tools.completed](#responsemcp_list_toolscompleted)
    - [response.mcp\_list\_tools.failed](#responsemcp_list_toolsfailed)
  - [MCP — call](#mcp--call)
    - [response.mcp\_call.in\_progress](#responsemcp_callin_progress)
    - [response.mcp\_call\_arguments.delta](#responsemcp_call_argumentsdelta)
    - [response.mcp\_call\_arguments.done](#responsemcp_call_argumentsdone)
    - [response.mcp\_call.completed](#responsemcp_callcompleted)
    - [response.mcp\_call.failed](#responsemcp_callfailed)

Source of truth: `openai==2.46.0`, `openai/types/responses/response_stream_event.py`
(`ResponseStreamEvent`, identical to `ResponsesServerEvent`). **53 event types.**

Every event carries two fields, omitted from the per-event schemas below:

```yaml
type: str            # the discriminator, values listed in the table
sequence_number: int # monotonic, per-stream, across ALL events
```

Referenced child shapes (not expanded — they are large):

| Reference | OpenAI type | Note |
|---|---|---|
| `<Response>` | `openai.types.responses.Response` | full response snapshot: `id`, `status`, `output[]`, `usage`, `error`, … |
| `<OutputItem>` | `ResponseOutputItem` | discriminated union of **28** item types (`message`, `reasoning`, `function_call`, `mcp_call`, …) |
| `<Logprob>` | `ResponseTextDeltaEvent.Logprob` | `{token, logprob, top_logprobs[]}` |
| `<Annotation>` | typed `object` on the wire | `url_citation` \| `file_citation` \| `container_file_citation` \| `file_path` |

## Addressing model

Three integer coordinates + one id locate everything. Which of them an event
carries tells you what it is about:

```
response                         -> response.*           (no coordinates)
└── output[output_index]         -> item_id              (an output item)
    ├── content[content_index]   -> + content_index      (a content part of a message / reasoning item)
    │   └── annotations[annotation_index]
    └── summary[summary_index]   -> + summary_index      (a reasoning summary part)
```

---

## Summary table

| Event type | Main fields | Link |
|---|---|---|
| **Response lifecycle** — 7 | | |
| `response.created` | `response: <Response>` | [↓](#responsecreated) |
| `response.in_progress` | `response: <Response>` | [↓](#responsein_progress) |
| `response.queued` | `response: <Response>` | [↓](#responsequeued) |
| `response.completed` | `response: <Response>` | [↓](#responsecompleted) |
| `response.incomplete` | `response: <Response>` | [↓](#responseincomplete) |
| `response.failed` | `response: <Response>` | [↓](#responsefailed) |
| `error` | `code`, `message`, `param` | [↓](#error) |
| **Output item lifecycle** — 2 | | |
| `response.output_item.added` | `output_index`, `item: <OutputItem>` | [↓](#responseoutput_itemadded) |
| `response.output_item.done` | `output_index`, `item: <OutputItem>` | [↓](#responseoutput_itemdone) |
| **Content part lifecycle** — 2 | | |
| `response.content_part.added` | `item_id`, `output_index`, `content_index`, `part` | [↓](#responsecontent_partadded) |
| `response.content_part.done` | `item_id`, `output_index`, `content_index`, `part` | [↓](#responsecontent_partdone) |
| **Assistant text** — 3 | | |
| `response.output_text.delta` | `item_id`, `output_index`, `content_index`, `delta`, `logprobs[]` | [↓](#responseoutput_textdelta) |
| `response.output_text.done` | `item_id`, `output_index`, `content_index`, `text`, `logprobs[]` | [↓](#responseoutput_textdone) |
| `response.output_text.annotation.added` | `item_id`, `output_index`, `content_index`, `annotation_index`, `annotation` | [↓](#responseoutput_textannotationadded) |
| **Refusal** — 2 | | |
| `response.refusal.delta` | `item_id`, `output_index`, `content_index`, `delta` | [↓](#responserefusaldelta) |
| `response.refusal.done` | `item_id`, `output_index`, `content_index`, `refusal` | [↓](#responserefusaldone) |
| **Reasoning — summary** — 4 | | |
| `response.reasoning_summary_part.added` | `item_id`, `output_index`, `summary_index`, `part.text` | [↓](#responsereasoning_summary_partadded) |
| `response.reasoning_summary_text.delta` | `item_id`, `output_index`, `summary_index`, `delta` | [↓](#responsereasoning_summary_textdelta) |
| `response.reasoning_summary_text.done` | `item_id`, `output_index`, `summary_index`, `text` | [↓](#responsereasoning_summary_textdone) |
| `response.reasoning_summary_part.done` | `item_id`, `output_index`, `summary_index`, `part.text`, `status` | [↓](#responsereasoning_summary_partdone) |
| **Reasoning — text** — 2 | | |
| `response.reasoning_text.delta` | `item_id`, `output_index`, `content_index`, `delta` | [↓](#responsereasoning_textdelta) |
| `response.reasoning_text.done` | `item_id`, `output_index`, `content_index`, `text` | [↓](#responsereasoning_textdone) |
| **Audio** — 4 | | |
| `response.audio.delta` | `delta` (base64) | [↓](#responseaudiodelta) |
| `response.audio.done` | — | [↓](#responseaudiodone) |
| `response.audio.transcript.delta` | `delta` | [↓](#responseaudiotranscriptdelta) |
| `response.audio.transcript.done` | — | [↓](#responseaudiotranscriptdone) |
| **Client-side tool calls** — 4 | | |
| `response.function_call_arguments.delta` | `item_id`, `output_index`, `delta` | [↓](#responsefunction_call_argumentsdelta) |
| `response.function_call_arguments.done` | `item_id`, `output_index`, `name`, `arguments` | [↓](#responsefunction_call_argumentsdone) |
| `response.custom_tool_call_input.delta` | `item_id`, `output_index`, `delta` | [↓](#responsecustom_tool_call_inputdelta) |
| `response.custom_tool_call_input.done` | `item_id`, `output_index`, `input` | [↓](#responsecustom_tool_call_inputdone) |
| **Server-side tool: web search** — 3 | | |
| `response.web_search_call.in_progress` | `item_id`, `output_index` | [↓](#responseweb_search_callin_progress) |
| `response.web_search_call.searching` | `item_id`, `output_index` | [↓](#responseweb_search_callsearching) |
| `response.web_search_call.completed` | `item_id`, `output_index` | [↓](#responseweb_search_callcompleted) |
| **Server-side tool: file search** — 3 | | |
| `response.file_search_call.in_progress` | `item_id`, `output_index` | [↓](#responsefile_search_callin_progress) |
| `response.file_search_call.searching` | `item_id`, `output_index` | [↓](#responsefile_search_callsearching) |
| `response.file_search_call.completed` | `item_id`, `output_index` | [↓](#responsefile_search_callcompleted) |
| **Server-side tool: image generation** — 4 | | |
| `response.image_generation_call.in_progress` | `item_id`, `output_index` | [↓](#responseimage_generation_callin_progress) |
| `response.image_generation_call.generating` | `item_id`, `output_index` | [↓](#responseimage_generation_callgenerating) |
| `response.image_generation_call.partial_image` | `item_id`, `output_index`, `partial_image_index`, `partial_image_b64` | [↓](#responseimage_generation_callpartial_image) |
| `response.image_generation_call.completed` | `item_id`, `output_index` | [↓](#responseimage_generation_callcompleted) |
| **Server-side tool: code interpreter** — 5 | | |
| `response.code_interpreter_call.in_progress` | `item_id`, `output_index` | [↓](#responsecode_interpreter_callin_progress) |
| `response.code_interpreter_call_code.delta` | `item_id`, `output_index`, `delta` | [↓](#responsecode_interpreter_call_codedelta) |
| `response.code_interpreter_call_code.done` | `item_id`, `output_index`, `code` | [↓](#responsecode_interpreter_call_codedone) |
| `response.code_interpreter_call.interpreting` | `item_id`, `output_index` | [↓](#responsecode_interpreter_callinterpreting) |
| `response.code_interpreter_call.completed` | `item_id`, `output_index` | [↓](#responsecode_interpreter_callcompleted) |
| **Server-side tool: MCP — tool listing** — 3 | | |
| `response.mcp_list_tools.in_progress` | `item_id`, `output_index` | [↓](#responsemcp_list_toolsin_progress) |
| `response.mcp_list_tools.completed` | `item_id`, `output_index` | [↓](#responsemcp_list_toolscompleted) |
| `response.mcp_list_tools.failed` | `item_id`, `output_index` | [↓](#responsemcp_list_toolsfailed) |
| **Server-side tool: MCP — call** — 5 | | |
| `response.mcp_call.in_progress` | `item_id`, `output_index` | [↓](#responsemcp_callin_progress) |
| `response.mcp_call_arguments.delta` | `item_id`, `output_index`, `delta` | [↓](#responsemcp_call_argumentsdelta) |
| `response.mcp_call_arguments.done` | `item_id`, `output_index`, `arguments` | [↓](#responsemcp_call_argumentsdone) |
| `response.mcp_call.completed` | `item_id`, `output_index` | [↓](#responsemcp_callcompleted) |
| `response.mcp_call.failed` | `item_id`, `output_index` | [↓](#responsemcp_callfailed) |

---

# Response lifecycle

Seven events about the response as a whole. The six `response.*` ones all carry
a **full snapshot** of the `Response` object — cheap to consume, expensive to
produce, which is why the SDK must own the accumulator.

Legal terminal states: `completed` | `incomplete` | `failed` | `cancelled`.

## response.created

```yaml
response: <Response>   # status="in_progress", output=[], usage=null
```

Always the first event of the stream. Announces the response `id`, the echoed
request parameters (`model`, `tools`, `temperature`, …) and nothing produced yet.

## response.in_progress

```yaml
response: <Response>   # status="in_progress"
```

The model has started working. Emitted immediately after `response.created` for a
direct run; after `response.queued` for a queued one. Snapshot is still empty.

## response.queued

```yaml
response: <Response>   # status="queued"
```

Only for `background: true` requests: the response is accepted but not yet
scheduled. Sits between `created` and `in_progress`.

## response.completed

```yaml
response: <Response>   # status="completed", output=[...all items...], usage=<ResponseUsage>
```

Terminal, success. The snapshot is the same object a non-streaming call would
have returned — this is where `usage` finally appears.

## response.incomplete

```yaml
response: <Response>   # status="incomplete", incomplete_details.reason="max_output_tokens"|"content_filter"
```

Terminal, partial. Generation stopped early but what was emitted is valid.

## response.failed

```yaml
response: <Response>   # status="failed", error={code, message}
```

Terminal, failure. The error is *inside* the snapshot.

## error

```yaml
code: str | null
message: str
param: str | null
```

The only event whose `type` is not prefixed `response.` — a stream-level error,
with no response snapshot attached. Usually followed by `response.failed`.

---

# Output item lifecycle

Two generic events that bracket **every** output item, whatever its kind. All 28
item types go through this pair; the item-specific events below are refinements
that happen *between* them.

## response.output_item.added

```yaml
output_index: int
item: <OutputItem>   # skeleton: id + type + status="in_progress", body empty
```

An item was appended to `response.output[]`. `item.id` is the `item_id` every
subsequent nested event will quote.

## response.output_item.done

```yaml
output_index: int
item: <OutputItem>   # fully populated, status="completed"|"incomplete"
```

The item is final. Carries the whole assembled item, so a client that ignores all
delta events can still reconstruct the response from `added`/`done` pairs alone.

---

# Content part lifecycle

Messages and reasoning items have an ordered `content[]` array. These two events
bracket each element of it.

## response.content_part.added

```yaml
item_id: str
output_index: int
content_index: int
part:                 # discriminated on type, body empty
  type: "output_text" | "refusal" | "reasoning_text"
```

## response.content_part.done

```yaml
item_id: str
output_index: int
content_index: int
part:                 # fully populated
  type: "output_text" | "refusal" | "reasoning_text"
```

---

# Assistant text

The `output_text` content part of a `message` item: open/delta/close, plus
out-of-band citation attachment.

## response.output_text.delta

```yaml
item_id: str
output_index: int
content_index: int
delta: str
logprobs: [<Logprob>]   # [] unless top_logprobs was requested
obfuscation: str        # optional padding, when stream_options.include_obfuscation
```

The token-by-token text stream. The only high-frequency event in the protocol.

## response.output_text.done

```yaml
item_id: str
output_index: int
content_index: int
text: str               # full concatenation of all deltas
logprobs: [<Logprob>]
```

Closes the text stream and restates the whole string, so a client may skip deltas.

## response.output_text.annotation.added

```yaml
item_id: str
output_index: int
content_index: int
annotation_index: int
annotation: <Annotation>   # url_citation | file_citation | container_file_citation | file_path
```

Attaches a citation to a *character range already emitted* (`start_index` /
`end_index` into the accumulated text). Interleaves with the deltas.

---

# Refusal

The `refusal` content part — same shape as text, different field names, no
logprobs and no annotations.

## response.refusal.delta

```yaml
item_id: str
output_index: int
content_index: int
delta: str
```

## response.refusal.done

```yaml
item_id: str
output_index: int
content_index: int
refusal: str            # note: "refusal", not "text"
```

---

# Reasoning — summary

A `reasoning` item has *two* parallel arrays: `summary[]` (user-visible
paraphrase, indexed by `summary_index`) and `content[]` (raw reasoning, indexed by
`content_index`). Summary parts get their own added/done pair — they are **not**
`content_part` events.

## response.reasoning_summary_part.added

```yaml
item_id: str
output_index: int
summary_index: int
part:
  type: "summary_text"
  text: str             # "" on open
```

## response.reasoning_summary_text.delta

```yaml
item_id: str
output_index: int
summary_index: int
delta: str
```

## response.reasoning_summary_text.done

```yaml
item_id: str
output_index: int
summary_index: int
text: str
```

## response.reasoning_summary_part.done

```yaml
item_id: str
output_index: int
summary_index: int
part:
  type: "summary_text"
  text: str
status: "incomplete" | null   # only event in this family with a status
```

`status: "incomplete"` means generation was interrupted mid-summary.

---

# Reasoning — text

Raw reasoning content. Unlike the summary, it *does* live in `content[]`, so it is
bracketed by the generic [`response.content_part.added`](#responsecontent_partadded) /
[`.done`](#responsecontent_partdone) pair with `part.type: "reasoning_text"`.

## response.reasoning_text.delta

```yaml
item_id: str
output_index: int
content_index: int
delta: str
```

## response.reasoning_text.done

```yaml
item_id: str
output_index: int
content_index: int
text: str
```

---

# Audio

The odd family out: **no `item_id`, no `output_index`** — audio is a response-level
side channel, not an output item. Two independent streams (PCM bytes and its
transcript) that run concurrently.

## response.audio.delta

```yaml
delta: str   # base64-encoded audio bytes
```

## response.audio.done

```yaml
{}   # type + sequence_number only
```

## response.audio.transcript.delta

```yaml
delta: str
```

## response.audio.transcript.done

```yaml
{}   # type + sequence_number only; the full transcript is NOT restated
```

---

# Client-side tool calls

Calls the **caller** must execute and feed back as input items on the next turn.
Both families stream a single opaque string payload; there is no separate
content-part layer — the item body *is* the stream. Bracketed by
`output_item.added` / `.done`.

## response.function_call_arguments.delta

```yaml
item_id: str
output_index: int
delta: str   # JSON fragment, NOT valid JSON on its own
```

Item type `function_call`. Concatenating all deltas yields `arguments`.

## response.function_call_arguments.done

```yaml
item_id: str
output_index: int
name: str        # the only delta/done pair that restates the tool name
arguments: str   # complete JSON string
```

## response.custom_tool_call_input.delta

```yaml
item_id: str
output_index: int
delta: str
```

Item type `custom_tool_call` — a free-form (non-JSON) tool payload.

## response.custom_tool_call_input.done

```yaml
item_id: str
output_index: int
input: str       # note: "input", not "arguments"
```

---

# Server-side tools

Tools the provider runs itself. Shared shape: a status machine over
`(item_id, output_index)` with **no payload** — the results land in the item body
delivered by `response.output_item.done`. Only image generation and code
interpreter stream anything.

## Web search

Item type `web_search_call`. Status path: `in_progress` → `searching` → `completed`.

### response.web_search_call.in_progress

```yaml
item_id: str
output_index: int
```

### response.web_search_call.searching

```yaml
item_id: str
output_index: int
```

### response.web_search_call.completed

```yaml
item_id: str
output_index: int
```

Results (`action`, `sources`) arrive only in the item's `output_item.done`.

## File search

Item type `file_search_call`. Same three-state path as web search.

### response.file_search_call.in_progress

```yaml
item_id: str
output_index: int
```

### response.file_search_call.searching

```yaml
item_id: str
output_index: int
```

### response.file_search_call.completed

```yaml
item_id: str
output_index: int
```

Matched chunks (`results[]` with `file_id`, `text`, `score`) arrive in `output_item.done`.

## Image generation

Item type `image_generation_call`. Status path: `in_progress` → `generating` →
(`partial_image`)* → `completed`.

### response.image_generation_call.in_progress

```yaml
item_id: str
output_index: int
```

### response.image_generation_call.generating

```yaml
item_id: str
output_index: int
```

### response.image_generation_call.partial_image

```yaml
item_id: str
output_index: int
partial_image_index: int    # 0-based
partial_image_b64: str      # a complete, renderable low-fidelity image
```

Progressive preview: each event is a *whole* image, not a byte-range chunk.

### response.image_generation_call.completed

```yaml
item_id: str
output_index: int
```

The final `result` (base64) is in `output_item.done`, not here.

## Code interpreter

Item type `code_interpreter_call`. Path: `in_progress` → (`code.delta`)* →
`code.done` → `interpreting` → `completed`. Note the discriminator inconsistency:
the code stream uses `..._call_code.` while the status events use `..._call.`.

### response.code_interpreter_call.in_progress

```yaml
item_id: str
output_index: int
```

### response.code_interpreter_call_code.delta

```yaml
item_id: str
output_index: int
delta: str   # source-code fragment
```

### response.code_interpreter_call_code.done

```yaml
item_id: str
output_index: int
code: str    # complete snippet
```

### response.code_interpreter_call.interpreting

```yaml
item_id: str
output_index: int
```

Code is written, sandbox is executing it.

### response.code_interpreter_call.completed

```yaml
item_id: str
output_index: int
```

`outputs[]` (`logs` / `image`) arrive in `output_item.done`.

## MCP — tool listing

Item type `mcp_list_tools`. Path: `in_progress` → `completed` | `failed`. No
`searching`-style middle state.

### response.mcp_list_tools.in_progress

```yaml
item_id: str
output_index: int
```

### response.mcp_list_tools.completed

```yaml
item_id: str
output_index: int
```

The discovered `tools[]` (name, `input_schema`, description) are in `output_item.done`.

### response.mcp_list_tools.failed

```yaml
item_id: str
output_index: int
```

The `error` string is in `output_item.done`.

## MCP — call

Item type `mcp_call`. The only server-side tool that also streams arguments, so
it mixes the client-side-tool shape with the status-machine shape. Path:
`in_progress` → (`arguments.delta`)* → `arguments.done` → `completed` | `failed`.

### response.mcp_call.in_progress

```yaml
item_id: str
output_index: int
```

### response.mcp_call_arguments.delta

```yaml
item_id: str
output_index: int
delta: str   # JSON fragment
```

### response.mcp_call_arguments.done

```yaml
item_id: str
output_index: int
arguments: str   # complete JSON string
```

### response.mcp_call.completed

```yaml
item_id: str
output_index: int
```

The tool `output` is in `output_item.done`.

### response.mcp_call.failed

```yaml
item_id: str
output_index: int
```

The `error` is in `output_item.done`.
