from typing import List

from langchain.schema.embeddings import Embeddings
from openai import AzureOpenAI


class OpenAIEmbeddings(Embeddings):
    client: AzureOpenAI
    azure_deployment: str

    def __init__(
        self,
        azure_deployment: str,
        azure_endpoint: str,
        openai_api_key: str,
        openai_api_version: str,
    ):
        self.client = AzureOpenAI(
            azure_deployment=azure_deployment,
            azure_endpoint=azure_endpoint,
            api_key=openai_api_key,
            api_version=openai_api_version,
        )
        self.azure_deployment = azure_deployment

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(
            model=self.azure_deployment, input=texts
        )
        return [e.embedding for e in response.data]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]
