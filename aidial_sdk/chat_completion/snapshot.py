import copy
import json

from pydantic import BaseModel

from aidial_sdk.utils.logging import logger
from aidial_sdk.utils.merge_chunks import cleanup_indices, merge_chunks


class StreamingResponseSnapshot(BaseModel):
    merged_chunks: dict = {}

    def add_delta(self, chunk: dict) -> None:
        logger.debug("chunk: " + json.dumps(chunk))
        self.merged_chunks = merge_chunks(self.merged_chunks, chunk)

    def to_block_response(self) -> dict:
        response = copy.deepcopy(self.merged_chunks)
        for choice in response.get("choices") or []:
            if "delta" in choice:
                choice["message"] = cleanup_indices(choice["delta"])
                del choice["delta"]
        response["object"] = "chat.completion"
        return response
