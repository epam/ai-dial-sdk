# Overview

An example of a simple text-to-text DIAL application served over the [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses).

It returns back the text of the last input message.

Upon start the Docker image exposes `openai/deployments/echo/responses` endpoint at port `5000`.

## Usage

Run the application:

```sh
python3 app.py
```

Send the next request:

```sh
curl http://127.0.0.1:5000/openai/deployments/echo/responses \
  -H "Content-Type: application/json" \
  -H "Api-Key: DIAL_API_KEY" \
  -d '{"input": "Repeat me!"}'
```

You will see the JSON response as (`id`, `created_at` and the message `id` vary per request):

```json
{
    "id": "resp_ebf5f2e4fb284b7c83fb6d0ac77dfa7a",
    "object": "response",
    "created_at": 1792147167,
    "model": "echo",
    "status": "completed",
    "output": [
        {
            "type": "message",
            "id": "msg_951b0e7253e6449caa82fcba408486f0",
            "role": "assistant",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": "Repeat me!",
                    "annotations": [],
                    "logprobs": []
                }
            ],
            "phase": null
        }
    ],
    "error": null,
    "incomplete_details": null,
    "usage": null,
    "tools": [],
    "tool_choice": "auto",
    "parallel_tool_calls": true,
    "instructions": null,
    "max_output_tokens": null,
    "max_tool_calls": null,
    "metadata": null,
    "prompt_cache_key": null,
    "reasoning": null,
    "safety_identifier": null,
    "temperature": null,
    "text": null,
    "top_logprobs": null,
    "top_p": null,
    "truncation": null,
    "user": null
}
```

Add `"stream": true` to the request body to receive the same response as a stream of Server-Sent Events, ending with `response.completed`.

Any OpenAI Responses API client works against the application unmodified, e.g. the `openai` Python client:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:5000/openai/deployments/echo",
    api_key="DIAL_API_KEY",
    default_headers={"Api-Key": "DIAL_API_KEY"},
)
print(client.responses.create(model="echo", input="Repeat me!").output_text)
```
