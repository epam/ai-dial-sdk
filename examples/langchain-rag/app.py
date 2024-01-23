"""
A simple RAG application.
"""

import os
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

import uvicorn
from langchain.callbacks.base import AsyncCallbackHandler
from langchain.chains import RetrievalQA
from langchain.chat_models import AzureChatOpenAI
from langchain.document_loaders import PyPDFLoader, WebBaseLoader
from langchain.embeddings import CacheBackedEmbeddings, OpenAIEmbeddings
from langchain.schema.output import ChatGenerationChunk, GenerationChunk
from langchain.storage import LocalFileStore
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Choice, Request, Response

DIAL_URL = os.getenv("DIAL_URL")

text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    chunk_size=256, chunk_overlap=0
)

embedding_store = LocalFileStore("./cache/")


class CustomCallbackHandler(AsyncCallbackHandler):
    def __init__(self, choice: Choice):
        self._choice = choice

    async def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        pass

    async def on_llm_new_token(
        self,
        token: str,
        *,
        chunk: Optional[Union[GenerationChunk, ChatGenerationChunk]] = None,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        self._choice.append_content(token)


class SimpleRAGApplication(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        collection_name = str(uuid4())

        with response.create_single_choice() as choice:
            first_user_message = request.messages[0].content or ""
            if first_user_message.endswith(".pdf"):
                loader = PyPDFLoader(first_user_message)
            else:
                loader = WebBaseLoader(first_user_message)

            openai_embedding = OpenAIEmbeddings(
                openai_api_base=DIAL_URL,
                openai_api_key=request.api_key,
                openai_api_version="2023-03-15-preview",
                openai_api_type="azure",
                max_retries=15,
                headers=(
                    {} if not request.jwt else {"Authorization": request.jwt}
                ),
            )

            embeddings = CacheBackedEmbeddings.from_bytes_store(
                openai_embedding,
                embedding_store,
                namespace=openai_embedding.model,
            )

            if len(request.messages) == 1:
                # Create the download stage to show to the user the active process.
                # After the loading is complete, the stage will auto finished.
                with choice.create_stage("Downloading the resource"):
                    try:
                        documents = loader.load()
                    except Exception:
                        choice.append_content(
                            "Error while loading the resource. Please check that the URL you provided is public and correct."
                        )
                        return

                # Show the user the total number of parts in the resource
                with choice.create_stage(
                    "Splitting the resource into parts"
                ) as stage:
                    texts = text_splitter.split_documents(documents)
                    stage.append_content(f"Total number of parts: {len(texts)}")

                # Show the user start of calculating embeddings stage
                with choice.create_stage("Calculating embeddings"):
                    docsearch = Chroma.from_documents(
                        texts, embeddings, collection_name=collection_name
                    )
                    docsearch.delete_collection()

                choice.append_content(
                    "The resource is loaded. Feel free to ask questions about it."
                )
            else:
                documents = loader.load()
                texts = text_splitter.split_documents(documents)
                docsearch = Chroma.from_documents(
                    texts, embeddings, collection_name=collection_name
                )

                # DIAL Api Key and authorization headers will be detected automatically and taken from the original application request
                # because propagation_auth_headers is enabled.
                # CustomCallbackHandler allows to pass tokens to the users as they are generated, so as not to wait for a complete response.
                llm = AzureChatOpenAI(
                    deployment_name="gpt-4",
                    model="gpt-4",
                    openai_api_base=DIAL_URL,
                    openai_api_key="-",
                    openai_api_version="2023-03-15-preview",
                    openai_api_type="azure",
                    temperature=0,
                    streaming=True,
                    callbacks=[CustomCallbackHandler(choice)],
                )

                with choice.create_stage("Generating the answer"):
                    await response.aflush()

                    qa = RetrievalQA.from_chain_type(
                        llm=llm,
                        chain_type="stuff",
                        retriever=docsearch.as_retriever(
                            search_kwargs={"k": 15, "fetch_k": 15}
                        ),
                    )

                    await qa.arun(request.messages[-1].content)

                    docsearch.delete_collection()


app = DIALApp(DIAL_URL, propagation_auth_headers=True)
app.add_chat_completion("simple-rag", SimpleRAGApplication())


if __name__ == "__main__":
    uvicorn.run(app, port=5000)
