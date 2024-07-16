from aidial_sdk.embeddings.base import Embeddings
from aidial_sdk.embeddings.request import Request
from aidial_sdk.embeddings.response import Embedding, Response, Usage


class SimpleEmbeddings(Embeddings):
    async def embeddings(self, request: Request) -> Response:
        n = 1
        if isinstance(request.input, list):
            n = len(request.input)
        return Response(
            data=[Embedding(embedding=[float(i)], index=i) for i in range(n)],
            model="dummy",
            usage=Usage(prompt_tokens=n, total_tokens=n),
        )
