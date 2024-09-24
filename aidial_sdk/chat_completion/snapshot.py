import copy
import json

from pydantic import BaseModel

from aidial_sdk.utils.logging import logger
from aidial_sdk.utils.merge_chunks import cleanup_indices, merge_chunks


class StreamingResponseSnapshot(BaseModel):
    n_expected: int

    chunk: dict = {}

    def generation_started(self) -> bool:
        return self.chunk != {}

    def create_choice(self) -> None:
        index = self.n_actual()
        self.add_delta({"choices": [{"index": index}]})

    def n_actual(self) -> int:
        ret = 0
        for choice in self.chunk.get("choices") or []:
            if (index := choice.get("index")) is not None:
                ret = max(ret, index + 1)
        return ret

    def has_all_choices(self) -> bool:
        return self.n_actual() == self.n_expected

    def add_delta(self, chunk: dict) -> None:
        logger.debug("chunk: " + json.dumps(chunk))
        self.chunk = merge_chunks(self.chunk, chunk)

    def to_block_response(self) -> dict:
        response = copy.deepcopy(self.chunk)
        for choice in response.get("choices") or []:
            if "delta" in choice:
                choice["message"] = cleanup_indices(choice["delta"])
                del choice["delta"]
        response["object"] = "chat.completion"
        return response
