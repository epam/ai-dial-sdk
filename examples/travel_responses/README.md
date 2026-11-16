# Overview

An example of an agent-like DIAL application served over the [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses): a travel concierge that writes a short trip brief for the cities it knows (Paris, Rome, Kyiv, Tokyo).

Where [echo_responses](../echo_responses) shows the smallest handler, this one shows most of what the SDK can put on the wire:

| Feature | Where in [`app/main.py`](app/main.py) |
|---|---|
| Reasoning text, a summary when `reasoning.summary` is asked, `encrypted_content` when `include` asks | `reason` |
| A `commentary` message before the tool calls, a `final_answer` one after | `call_weather`, `answer` |
| Parallel calls of the client's `get_weather` function, streamed side by side; one at a time with `parallel_tool_calls: false`, none with `tool_choice: "none"` | `call_weather` |
| A `web_search_call` with its query and sources, when the `web_search` tool is enabled | `answer` |
| `url_citation` annotations over the exact span they cite | `answer` |
| An `image_generation_call` with partial images, when the `image_generation` tool is enabled and a postcard is asked for | `answer` |
| `max_output_tokens`: the answer stops short with `status: "incomplete"` | `answer` |
| A refusal, for a request to book or pay | `create_response` |
| An HTTP 400 and no stream, for an empty question | `create_response` |
| Usage, with reasoning tokens | both turns |

The application is laid out as:

- [`app/main.py`](app/main.py) — the application itself: everything it puts on the wire, through the SDK's builders.
- [`app/tools.py`](app/tools.py) — the tool traffic of a request: which tools the client enabled, and the `function_call_output`s it sent back, paired with their calls by `call_id`.
- [`app/model.py`](app/model.py) — a scripted stand-in for a language model: its decisions, its text and a token stream paced like a model's. It runs offline and answers the same way every time; a real application calls a model here.

It's stateless, as the SDK is: the client sends the whole conversation with every request.

It doesn't show custom tool calls, logprobs or `unsafe_emit`.

Upon start the Docker image exposes `openai/deployments/travel/responses` endpoint at port `5000`.

## Usage

Run the application:

```sh
python3 -m app
```

Ask for a trip, declaring the `get_weather` tool the client implements:

```sh
curl http://127.0.0.1:5000/openai/deployments/travel/responses \
  -H "Content-Type: application/json" \
  -H "Api-Key: DIAL_API_KEY" \
  -d '{
    "input": "Plan a trip to Paris and Rome",
    "tools": [{
      "type": "function",
      "name": "get_weather",
      "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"]
      }
    }]
  }'
```

The response ends the turn with two calls for the client to run (ids vary per request, the rest of the response is left out):

```json
{
    "status": "completed",
    "output": [
        {"type": "reasoning", "summary": [], "content": [{"type": "reasoning_text", "text": "The user plans a trip to Paris and Rome. I need the weather first, so I call get_weather."}], "...": "..."},
        {"type": "message", "phase": "commentary", "content": [{"type": "output_text", "text": "Checking the weather in Paris and Rome.", "...": "..."}], "...": "..."},
        {"type": "function_call", "name": "get_weather", "arguments": "{\"city\": \"Paris\"}", "call_id": "call_6dfba1c20e72404987c1e7df03e5be3f", "...": "..."},
        {"type": "function_call", "name": "get_weather", "arguments": "{\"city\": \"Rome\"}", "call_id": "call_5e0a337c39dc4392944f3dbd906359ca", "...": "..."}
    ],
    "usage": {"input_tokens": 7, "output_tokens": 29, "total_tokens": 36, "...": "..."}
}
```

Add `"stream": true` to see the same as Server-Sent Events, the deltas of the two calls interleaved.

The whole loop, with the `openai` Python client: run the calls, send everything back, get the brief.

```python
import json

from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:5000/openai/deployments/travel",
    api_key="DIAL_API_KEY",
    default_headers={"Api-Key": "DIAL_API_KEY"},
)

tools = [
    {
        "type": "function",
        "name": "get_weather",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
    {"type": "web_search"},
    {"type": "image_generation"},
]


def get_weather(city: str) -> str:
    return {"Paris": "sunny, 24°C", "Rome": "cloudy, 19°C"}[city]


history = [{"role": "user", "content": "Plan a trip to Paris and Rome, with a postcard"}]
first = client.responses.create(model="travel", input=history, tools=tools)

# Run the calls the deployment asked for, and send everything back
history += first.output
for item in first.output:
    if item.type == "function_call":
        output = get_weather(**json.loads(item.arguments))
        history.append(
            {"type": "function_call_output", "call_id": item.call_id, "output": output}
        )

second = client.responses.create(model="travel", input=history, tools=tools)
print(second.output_text)
print([item.type for item in second.output])
```

It prints:

```text
Your trip brief:
- Paris: sunny, 24°C. Don't miss the Louvre.
- Rome: cloudy, 19°C. Don't miss the Colosseum.

['reasoning', 'web_search_call', 'message', 'image_generation_call']
```
