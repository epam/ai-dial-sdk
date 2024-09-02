import copy
import json

from pydantic import BaseModel

from aidial_sdk.utils.logging import logger
from aidial_sdk.utils.merge_chunks import cleanup_indices, merge


class StreamingResponseSnapshot(BaseModel):
    merged_chunks: dict = {}

    def add_delta(self, chunk: dict) -> None:
        # Avoid merging top-level atomic fields
        # like "id", "created", "model", "object", "system_fingerprint".
        # Non-atomic field like "choice" will be merged following
        # the standard merging procedure.

        logger.debug("chunk: " + json.dumps(chunk))

        chunk = chunk.copy()

        for key in ["id", "created", "model", "object", "system_fingerprint"]:
            if key in chunk and chunk[key] is not None:
                self.merged_chunks[key] = chunk[key]
                del chunk[key]

        self.merged_chunks = merge(self.merged_chunks, chunk)

    def to_block_response(self) -> dict:
        response = copy.deepcopy(self.merged_chunks)
        for choice in response.get("choices") or []:
            if "delta" in choice:
                choice["message"] = cleanup_indices(choice["delta"])
                del choice["delta"]
        response["object"] = "chat.completion"
        return response
