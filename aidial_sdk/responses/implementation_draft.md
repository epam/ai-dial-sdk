# DIAL Responses API SDK — implementation draft

> Companion to [design_draft.md](./design_draft.md), which is the source of truth
> for the API surface. This file is the sequencing plan to work through once the
> design is approved, organised by the three delivery rounds.

## Round 1 — [vanilla Responses API](./round_1_vanilla_responses.md)

The chat completion package maps onto this design closely enough that most files
have a direct counterpart, which keeps the work reviewable in small pieces.

| step | deliverable | verify |
|---|---|---|
| 1.1 | `responses/request.py` — models, the input-item union, `RawItem` fallback, navigation helpers, stateful-field rejection | round-trip tests over recorded OpenAI Responses payloads; unknown item types survive |
| 1.2 | `responses/events.py` — the event dataclasses (counterpart of `chat_completion/chunks.py`), owning `sequence_number` / index assignment | golden-file tests: builder call sequence → exact SSE transcript |
| 1.3 | `responses/response.py` + item builders (message, text part, reasoning, function call, custom tool call, raw), snapshot accumulation | the same handler produces a consistent snapshot in `stream: true` and `stream: false`; guard-rail errors |
| 1.4 | `responses/base.py`, `DIALApp.add_responses`, the `rate` route, heartbeats, error paths | end-to-end tests through `TestClient`, streaming and block; error before/after first flush |
| 1.5 | `examples/echo` ported, README section | run it against a local DIAL |

## Round 2 — [DIAL features](./round_2_dial_features.md)

Additive only. Nothing in round 1 changes; the round-1 test suite must keep
passing untouched.

| step | deliverable | verify |
|---|---|---|
| 2.1 | request-side extensions: `custom_content`, `custom_fields`, `max_prompt_tokens`, `File`, `files()`, the `state` / `form_value` / `configuration` helpers | parse fixtures captured from DIAL Chat |
| 2.2 | `responses/stage.py` + the `custom_content` encoding in `events.py` | golden-file SSE tests for stages interleaved with text; carrier-message creation when a stage precedes any text |
| 2.3 | `add_file` on `Message` and `Stage`; `set_state`, `set_form_schema` | round-1 payloads byte-identical when no DIAL feature is used |
| 2.4 | `statistics`: `add_usage_per_model`, `set_discarded_input_items`; `CacheBreakpointPath.input_items` | values match the chat completion payload for the same inputs |
| 2.5 | `aidial_sdk.forms` extraction + re-exports; the `configuration` route | existing chat completion form tests unchanged |
| 2.6 | `examples/langchain_rag` and `examples/tic_tac_toe` ported | run them against a local DIAL |

## Round 3 — [improvements](./round_3_improvements.md)

Unordered and independent; each item is its own PR with its own trigger. Nothing
to sequence in advance.

## Notes

Two decisions worth fixing before step 1.1:

- **The snapshot is the source of truth.** Items write into the accumulating
  response object and *derive* events from those writes, rather than the chat
  completion arrangement where chunks are the source of truth and the block
  response is merged back out of them. This removes `merge_chunks` /
  `cleanup_indices` from the Responses path entirely and guarantees streaming and
  block modes agree by construction.
- **Wire mapping behind one seam.** The translation from builder writes to events
  should sit in a single module (`events.py`) with no application-visible surface.
  This is what lets round 2 add the `custom_content` encoding without touching the
  round-1 builders, and what keeps the two encoding revisits in round 3 — stages
  as a dedicated item type, forms as a custom tool call — local changes rather
  than SDK-wide migrations.
