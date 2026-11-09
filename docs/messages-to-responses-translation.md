# Anthropic Messages to OpenAI Responses request/response mapping

The translator serves the Anthropic Messages API by a Responses API handler of the application, or by DIAL Core (see the [setup](../README.md#anthropic-messages-to-responses-translator)). This page documents how every parameter is translated in both directions.

- [Endpoints](#endpoints)
- [Request: Anthropic → Responses](#request-anthropic--responses)
- [Response: Responses → Anthropic](#response-responses--anthropic)
- [Streaming: Responses events → Anthropic SSE](#streaming-responses-events--anthropic-sse)
- [Errors](#errors)

## Endpoints

| Client calls | Served by |
| --- | --- |
| `POST /anthropic/v1/messages` (configurable) of `expose_as_anthropic_messages` | The decorated handler, called in-process |
| `POST /openaiResponses/anthropic/v1/messages` of `mount_translator` | `POST {DIAL_URL}/openai/v1/responses` |

Any other path of the mount, `count_tokens` included, returns an Anthropic-shaped 404.

The handler gets the headers of the Messages request. DIAL Core gets only these ones:

| Header | Why |
| --- | --- |
| `api-key` | Core's per-request key that authenticates the call back to Core |
| `x-dial-cache-policy` | The prompt caching policy of the request |
| `x-upstream-id` | Pins the request to the same upstream |

## Request: Anthropic → Responses

As with the [Chat Completions translator](messages-to-chat-translation.md#request-anthropic--chat-completions), the request body isn't validated against a schema: a missing or mistyped field fails with 500.

### Top-level parameters

| Anthropic (`/v1/messages`) | Responses | Notes |
| --- | --- | --- |
| `model` | `model` | The handler gets it as is. DIAL Core gets the deployment from the `x-dial-deployment-id` header, falling back to the `x-dial-override-name` header |
| `messages` | `input` | See the messages section below |
| `system` | `instructions` | Text blocks are joined with `\n\n`; other blocks are dropped with a warning. An empty system sends nothing |
| `max_tokens` | `max_output_tokens` | A positive budget below 16, the Responses API minimum, is raised to 16 (e.g. the one-token probes of Claude Code) |
| `temperature`, `top_p` | `temperature`, `top_p` | Passed through as-is |
| `tools` | `tools`, `max_tool_calls` | See the tools section below |
| `tool_choice` | `tool_choice`, `parallel_tool_calls` | See the tool_choice section below |
| `thinking`, `output_config.effort` | `reasoning` | See the thinking section below |
| `output_config.format` | `text` | `{"format": {"type": "json_schema", "name": "response", "schema": ..., "strict": true}}`. Dropped with a warning unless `type` is `json_schema` with a nonempty `schema` |
| `metadata.user_id` | `user` | Only up to 64 characters, the Responses API limit: a longer id is dropped rather than truncated into another user's id |
| `service_tier` | `service_tier` | `auto` → `auto`, `standard_only` → `default`; other values are dropped |
| `stream` | `stream` | |
| — | `store: false` | Always: the Messages API keeps no state between the requests |
| — | `include: ["reasoning.encrypted_content"]` | Always: replays the reasoning of the previous turns, see below |
| `stop_sequences`, `top_k`, `compaction`, `context_management`, `mcp_servers`, `container`, `inference_geo` | — | Dropped with a warning |
| `cache_control` at any level | — | Dropped |

### How messages get converted

`tool_result` and `tool_use` blocks become `input` items of their own, and system text stays where the client put it.

| Anthropic message | Responses `input` items |
| --- | --- |
| `user` role, string content | `{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "..."}]}`; an empty string sends nothing |
| `user` role, content blocks | A `function_call_output` per `tool_result`, then a `system` message per `mid_conv_system` block, then a `user` message with the remaining parts |
| `assistant` role, string content | `{"type": "message", "role": "assistant", "content": "..."}` |
| `assistant` role, content blocks | A `system` message per `mid_conv_system` block, then the blocks in order: adjacent text joined with `\n` as an `assistant` message, a `reasoning` item per replayed thinking, a `function_call` per `tool_use` |
| `system` role | A `system` message at the same position |
| `system` role with `clear_at: next_user_message` | Sent only while no later `user` message exists |
| `system` role with `output_config.effort` | The per-turn effort; see the thinking section below |
| Final `assistant` message (prefill) | Sent as ordinary history, not as a prefix to continue |
| Any other role | 400 `invalid_request_error` |

### Content blocks

| Anthropic block | Responses | Notes |
| --- | --- | --- |
| `text` | `{"type": "input_text", "text": "..."}` | In an assistant turn, part of the message `content` |
| `image`, `base64` source | `{"type": "input_image", "image_url": "data:<media_type>;base64,<data>", "detail": "auto"}` | |
| `image`, `url` source | `{"type": "input_image", "image_url": "<url>", "detail": "auto"}` | |
| `document`, `base64` source | `{"type": "input_file", "filename": "<title>", "file_data": "data:..."}` | Defaults: `document.pdf`, `application/pdf` |
| `document`, `url` source | `{"type": "input_file", "file_url": "<url>"}` | |
| `document`, `text` source | `{"type": "input_text", "text": "..."}` | |
| `document`, `content` source | Its text and image blocks as parts | |
| `image` or `document`, `file` source | — | 400 `invalid_request_error`: files uploaded via Anthropic Files API aren't supported |
| `search_result` | `{"type": "input_text", "text": "<title>\n<source>\n\n<text>"}` | Text blocks are joined with `\n`; citation metadata is lost |
| `tool_result` | `{"type": "function_call_output", "call_id": "...", "output": ...}` | Text only: `output` is the text joined with `\n`, `is_error` prefixes `Error: `. With images or documents: `output` is the array of the parts, so they stay with the call they answer, and `is_error` prepends an `Error:` part. `tool_reference` blocks are dropped |
| `tool_use` | `{"type": "function_call", "call_id": "...", "name": "...", "arguments": "<JSON string>"}` | |
| `compaction` (replayed) | Its summary text | A failed compaction (`content: null`) sends nothing |
| `mid_conv_system` | A `system` message | |
| `thinking`, `redacted_thinking` carrying a reasoning item | `{"type": "reasoning", "id": "...", "encrypted_content": "...", "summary": [...]}` | See reasoning replay below |
| Any other `thinking`, `redacted_thinking` | — | Dropped: another provider can't verify the signature |
| Any other block | — | Dropped with a warning |

### Reasoning replay

A reasoning item comes back to the client in the `signature` of a `thinking` block, or in the `data` of a `redacted_thinking` block when it has no text, as the JSON string:

```json
{"dial_translator_reasoning_wrapper":{"version":2,"id":"rs_…","encrypted_content":"…"}}
```

Replayed, such a block becomes the reasoning item again, with the thinking text as its summary, which lets a stateless request (`store: false`) continue the reasoning of the previous turns. The id and the encrypted content are passed through untouched.

### tools

No tool is ever dropped: a tool the deployment can't run fails the request with the deployment's own error.

| Anthropic tool | Responses tool |
| --- | --- |
| Custom tool (no `type`, or `type: "custom"`) | `{"type": "function", "name": "...", "description": "...", "parameters": <input_schema>, "strict": <tool's strict>}` |
| `web_search_*` | `{"type": "web_search", "filters": {"allowed_domains": [...]}, "user_location": {...}}` |
| Any other type (`bash_*`, `text_editor_*`, `computer_*`, …) | Forwarded as sent |

- `strict` is always sent: `true` only when the tool says so.
- `parameters` drops the schema's root `$schema` key.
- The `max_uses` of the web search becomes the request's `max_tool_calls`, which caps all the built-in tools together: with several web search tools, it is dropped with a warning. `blocked_domains` is dropped with a warning.
- A function name is aliased as in the [Chat Completions translator](messages-to-chat-translation.md#tools), in `tools`, `tool_choice` and replayed `function_call` items, and restored in the response.

### tool_choice

| Anthropic `tool_choice` | Responses `tool_choice` |
| --- | --- |
| `{"type": "auto"}` | `"auto"` |
| `{"type": "any"}` | `"required"` |
| `{"type": "none"}` | `"none"` |
| `{"type": "tool", "name": "..."}` | `{"type": "function", "name": "..."}` |
| `{"type": "tool", "name": "..."}` naming the web search tool | `{"type": "allowed_tools", "mode": "required", "tools": [{"type": "web_search"}]}` |
| `disable_parallel_tool_use: true` / `false` | `parallel_tool_calls: false` / `true` |

### thinking → reasoning

The effort follows the [Chat Completions rule](messages-to-chat-translation.md#thinking--reasoning_effort), as `reasoning.effort`. Unlike Anthropic, the Responses API returns no reasoning text unless it's asked for a summary:

| Anthropic | `reasoning` |
| --- | --- |
| `thinking.type: "disabled"` | `{"effort": "none"}` |
| An effort | `effort` |
| `thinking` other than `disabled`, without `display: "omitted"` | `summary: "auto"` |
| Neither | Not sent: the deployment's default applies |

For example, Claude Code's `thinking: {"type": "adaptive"}` with `output_config.effort: "high"` becomes `{"effort": "high", "summary": "auto"}`.

## Response: Responses → Anthropic

Output items are converted in order.

| Responses field | Anthropic response field | Notes |
| --- | --- | --- |
| `id` | `id` | |
| — | `model` | The `x-dial-deployment-id` header, falling back to the `x-dial-override-name` header, then to the request's `model`: the upstream's `model` is not exposed |
| `reasoning` item with text and `encrypted_content` | `{"type": "thinking", "thinking": "...", "signature": "<the reasoning item>"}` | The summary and content texts are joined with `\n\n` |
| `reasoning` item with `encrypted_content` only | `{"type": "redacted_thinking", "data": "<the reasoning item>"}` | |
| `reasoning` item with text only | `{"type": "thinking", "thinking": "...", "signature": ""}` | Not replayable |
| `message` → `output_text` | `{"type": "text", "text": "..."}` | |
| `message` → `output_text.annotations[]` `url_citation` | `server_tool_use` + `web_search_tool_result` after that text | Each URL once per response; `query` is `""` |
| `message` → `refusal` | `{"type": "text", "text": "..."}` | |
| `function_call` | `{"type": "tool_use", "id": "<call_id>", "name": "...", "input": {...}}` | `arguments` is JSON-parsed; invalid or non-object JSON becomes `{}` |
| Any other item | — | A `web_search_call` is counted in `usage` |
| No content at all | `{"type": "text", "text": ""}` | The SDKs index `content[0]` |
| `status: "failed"` | An error | See Errors below |

### stop_reason

| Condition (first match wins) | `stop_reason` |
| --- | --- |
| `incomplete_details.reason: "max_output_tokens"` | `max_tokens`, even with a function call: it is the one cut off |
| `incomplete_details.reason: "content_filter"` | `refusal` |
| Any function call | `tool_use` |
| A refusal | `refusal` |
| Everything else | `end_turn` |

### usage

As in the [Chat Completions translator](messages-to-chat-translation.md#usage), the three Anthropic input counters add up to the Responses `input_tokens`.

| Anthropic `usage` | Responses `usage` |
| --- | --- |
| `input_tokens` | `input_tokens` − cache read − cache write |
| `cache_read_input_tokens` | `input_tokens_details.cached_tokens` |
| `cache_creation_input_tokens` | `input_tokens_details.cache_write_tokens` |
| `output_tokens` | `output_tokens` (includes reasoning) |
| `output_tokens_details.thinking_tokens` | `output_tokens_details.reasoning_tokens` |
| `server_tool_use.web_search_requests` | `web_search_call` items with a `search` action |
| `server_tool_use.web_fetch_requests` | `web_search_call` items with an `open_page` action |

## Streaming: Responses events → Anthropic SSE

The client gets `message_start → (content_block_start → delta* → content_block_stop)* → message_delta → message_stop`, with one block open at a time.

| Responses event | Anthropic events |
| --- | --- |
| `response.created` | `message_start` (zero usage) |
| `response.output_text.delta`, `response.refusal.delta` | `text` block, `text_delta` |
| `response.reasoning_summary_text.delta`, `response.reasoning_text.delta` | `thinking` block, `thinking_delta`; `\n\n` between the parts |
| `response.output_item.added` with a `function_call` | `tool_use` block (`input: {}`) |
| `response.function_call_arguments.delta` | `input_json_delta` |
| `response.output_item.done` with a `function_call` | The whole arguments, only if no deltas came; then the block stops |
| `response.output_item.done` with a `reasoning` | The thinking block gets the reasoning item as its `signature_delta` and stops. Without streamed text, a whole `thinking` or `redacted_thinking` block |
| `response.output_item.done` with a `message` | A `server_tool_use` + `web_search_tool_result` pair for its new cited URLs |
| `response.completed`, `response.incomplete` | Open blocks close, then `message_delta` (stop reason, usage) + `message_stop`. A stream with no content gets one empty `text` block |
| `response.failed`, `error` | `error` event; see Errors below |
| An SSE comment (a heartbeat) | `ping` |
| Any other event | — |
| End of stream without `response.completed` or `response.incomplete` | `error` event (`api_error`): the answer may be cut off |

## Errors

Every error is Anthropic-shaped: `{"type": "error", "error": {"type": "...", "message": "..."}}`. The `error.type` follows the HTTP status, as in the [Chat Completions translator](messages-to-chat-translation.md#errors).

| Failure | HTTP status |
| --- | --- |
| Invalid JSON, unknown role, bad effort, `image` or `document` with a `file` source | 400 |
| An error response of the handler or DIAL Core | The same, with its `error.message` (or the body, when it isn't JSON) and, for the handler, its headers |
| An exception of the handler | What the app's exception handler for it answers, otherwise the status of a DIAL SDK `HTTPException`, otherwise 500 |
| DIAL Core unreachable | 502 |
| `DIAL_URL` unset for the mount | 500 |
| `status: "failed"` or an `error` event with `rate_limit_exceeded`, `vector_store_timeout` | 429, 504 |
| `status: "failed"` or an `error` event with `invalid_request_error`, `context_length_exceeded`, or a code blaming the prompt or an image (`invalid_prompt`, `bio_policy`, `invalid_image`, `image_too_large`, …) | 400 |
| `status: "failed"` or an `error` event with any other code | 500 |

Once a stream has started, a failure becomes a final `error` event of the same type.
