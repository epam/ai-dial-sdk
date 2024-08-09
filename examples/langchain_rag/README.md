## Overview

An example of a simple DIAL RAG application based on Langchain utilizing Chroma vector database and RetrievalQA chain.

The application processes chat completion request in the following way:

1. finds the last attachment in the conversation history and extracts URL from it,
2. downloads the document from the URL,
3. parses the document if it's a PDF or treats it as a plain text otherwise,
4. splits the text of the document into chunks,
5. computes the embeddings for the chunks,
6. saves the embeddings in the local cache,
7. run the RetrievalQA Langchain chain that consults the embeddings store and calls chat completion model to generate final answer.

Upon start the Docker image exposes `openai/deployments/simple-rag/chat/completions` endpoint at port `5000`.

## Configuration

|Variable|Default|Description|
|---|---|---|
|DIAL_URL||Required. URL of the DIAL server. Used to access embeddings and chat completion models|
|EMBEDDINGS_MODEL|text-embedding-ada-002|Embeddings model|
|CHAT_MODEL|gpt-4|Chat completion model|
|API_VERSION|2024-02-01|Azure OpenAI API version|
|LANGCHAIN_DEBUG|False|Flag to enable debug logs from Langchain|
|OPENAI_LOG||Flag that controls openai library logging. Set to `debug` to enable debug logging|

## Usage

The application could be tested by running it directly on your machine:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app
```

Then you may call the application using DIAL API key:

```sh
curl "http://localhost:5000/openai/deployments/simple-rag/chat/completions" \
  -X POST \
  -H "Content-Type: application:json" \
  -H "api-key:${DIAL_API_KEY}" \
  -d '{
  "stream": true,
  "messages": [
    {
      "role": "user",
      "content": "Who is Miss Meyers?",
      "custom_content": {
        "attachments": [
          {
            "url": "https://en.wikipedia.org/wiki/Miss_Meyers"
          }
        ]
      }
    }
  ]
}'
```