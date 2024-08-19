"""
A simple application,that search over attached images by text query,
using multi-modal embeddings for search
"""

import os
from uuid import uuid4

import uvicorn
from attachment import get_image_attachments
from embeddings import ImageDialEmbeddings
from vector_store import DialImageVectorStore

from aidial_sdk import DIALApp
from aidial_sdk import HTTPException as DIALException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


def get_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"Please provide {name!r} environment variable")
    return value


DIAL_URL = get_env("DIAL_URL")
EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "multimodalembedding@001")
EMBEDDINGS_DIMENSIONS = int(os.getenv("EMBEDDINGS_DIMENSIONS") or "1408")


class ImageSearchApplication(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        with response.create_single_choice() as choice:
            message = request.messages[-1]
            user_query = message.content

            if not user_query:
                raise DIALException(
                    message="Please provide search query", status_code=400
                )

            image_attachments = get_image_attachments(request.messages)
            if not image_attachments:
                msg = "No attachment with DIAL Storage URL was found"
                raise DIALException(
                    status_code=422,
                    message=msg,
                    display_message=msg,
                )
            # Create a new local vector store to store image embeddings
            vector_store = DialImageVectorStore(
                collection_name=str(uuid4()),
                embedding_function=ImageDialEmbeddings(
                    dial_url=DIAL_URL,
                    embeddings_model=EMBEDDINGS_MODEL,
                    dimensions=EMBEDDINGS_DIMENSIONS,
                ),
            )
            # Show user that embeddings of images are being calculated
            with choice.create_stage("Calculating image embeddings"):
                # For simplicity of  example let's take only images,
                # that are uploaded to DIAL Storage already
                await vector_store.aadd_images(
                    uris=[att.url for att in image_attachments if att.url],
                    metadatas=[
                        {"url": att.url, "type": att.type, "title": att.title}
                        for att in image_attachments
                        if att.url
                    ],
                )

            # Show user that the search is being performed
            with choice.create_stage("Searching for most relevant image"):
                search_result = await vector_store.asimilarity_search(
                    query=user_query, k=1
                )

            if len(search_result) == 0:
                msg = "No relevant image found"
                raise DIALException(
                    status_code=404,
                    message=msg,
                    display_message=msg,
                )

            top_result = search_result[0]
            choice.add_attachment(
                url=top_result.metadata["url"],
                title=top_result.metadata["title"],
                type=top_result.metadata["type"],
            )
            vector_store.delete_collection()


app = DIALApp(DIAL_URL, propagate_auth_headers=True)
app.add_chat_completion("image-search", ImageSearchApplication())


if __name__ == "__main__":
    uvicorn.run(app, port=5000)
