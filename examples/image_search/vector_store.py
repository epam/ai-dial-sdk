from typing import List, Optional

from langchain_community.vectorstores import Chroma
from langchain_core.runnables.config import run_in_executor


class DialImageVectorStore(Chroma):
    def encode_image(self, uri: str) -> str:
        """
        Overload of Chroma encode_image method, that does not download image content
        """
        return uri

    async def aadd_images(
        self, uris: List[str], metadatas: Optional[List[dict]] = None
    ):
        """
        Async version of add_images, that is present in Chroma
        """
        return await run_in_executor(None, self.add_images, uris, metadatas)
