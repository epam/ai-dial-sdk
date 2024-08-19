from typing import List

import httpx
from langchain_core.embeddings import Embeddings


class ImageDialEmbeddings(Embeddings):
    def __init__(
        self,
        dial_url: str,
        embeddings_model: str,
        dimensions: int,
    ) -> None:
        self._dial_url = dial_url
        self._embeddings_url = (
            f"{self._dial_url}/openai/deployments/{embeddings_model}/embeddings"
        )
        self._dimensions = dimensions
        self._client = httpx.Client()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError(
            "This embeddings should not be used with text documents"
        )

    def embed_query(self, text: str) -> List[float]:
        # Auth headers are propagated by the DIALApp
        response = self._client.post(
            self._embeddings_url,
            json={"input": [text], "dimensions": self._dimensions},
        )
        data = response.json()
        assert data.get("data") and len(data.get("data")) == 1
        return data.get("data")[0].get("embedding")

    def embed_image(self, uris: List[str]) -> List[List[float]]:
        result = []
        for uri in uris:
            # Auth headers are propagated by the DIALApp
            response = self._client.post(
                self._embeddings_url,
                json={
                    "input": [],
                    "dimensions": self._dimensions,
                    "custom_input": [
                        {
                            "type": "image/png",
                            "url": uri,
                        }
                    ],
                },
            )
            data = response.json()
            assert data.get("data") and len(data.get("data")) == 1
            result.append(data.get("data")[0].get("embedding"))
        assert len(result) == len(uris)
        return result
