# DIAL Responses API SDK — implementation draft

> Companion to [design_draft.md](./design_draft.md), which is the source of
> truth for the API surface and the wire-format decisions. This file is the
> sequencing plan to work through once the design is approved.

## Sequencing

The chat completion package maps onto this design closely enough that most files
have a direct counterpart, which keeps the work reviewable in small pieces.

| step | deliverable | verify |
|---|---|---|
| 1 | `responses/request.py` — models, `RawItem` fallback, navigation helpers, stateful-field rejection | round-trip tests over recorded OpenAI Responses payloads; unknown item types survive |
| 2 | `responses/events.py` — the event dataclasses (counterpart of `chat_completion/chunks.py`), owning `sequence_number` / index assignment | golden-file tests: builder call sequence → exact SSE transcript |
| 3 | `responses/response.py` + item builders, snapshot accumulation | the same handler produces a consistent snapshot in `stream: true` and `stream: false`; guard-rail errors |
| 4 | `responses/base.py`, `DIALApp.add_responses`, heartbeats, error paths | end-to-end tests through `TestClient`, streaming and block; error before/after first flush |
| 5 | `aidial_sdk.forms` extraction + re-exports | existing chat completion form tests unchanged |
| 6 | `examples/echo` and `examples/langchain_rag` ported to Responses, README section | run them against a local DIAL |

## Notes

Two decisions worth fixing before step 1:

- **The snapshot is the source of truth.** Items write into the accumulating
  response object and *derive* events from those writes, rather than the chat
  completion arrangement where chunks are the source of truth and the block
  response is merged back out of them. This removes `merge_chunks` /
  `cleanup_indices` from the Responses path entirely and guarantees streaming and
  block modes agree by construction.
- **Wire mapping behind one seam.** The translation from builder writes to events
  should sit in a single module (`events.py`) with no application-visible surface.
  The DIAL extensions are encoded inside `custom_content` of the assistant message
  ([decisions 1 and 2](./design_draft.md#protocol-decisions-made)), and that
  encoding is the part most likely to be revisited — a dedicated stage item type
  remains the cleaner shape if ordering ever matters to DIAL Chat. Keeping the
  mapping in one file makes that a local change instead of an SDK-wide migration.
