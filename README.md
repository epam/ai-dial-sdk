<h1 align="center">
    AI DIAL Python SDK
</h1>
<p align="center">
    <p align="center">
    <a href="https://dialx.ai/">
        <img src="https://dialx.ai/logo/dialx_logo.svg" alt="About DIALX">
    </a>
</p>
<h4 align="center">
    <a href="https://pypi.org/project/aidial-sdk/">
        <img src="https://img.shields.io/pypi/v/aidial-sdk.svg" alt="PyPI version">
    </a>
    <a href="https://discord.gg/ukzj9U9tEe">
        <img src="https://img.shields.io/static/v1?label=DIALX%20Community%20on&message=Discord&color=blue&logo=Discord&style=flat-square" alt="Discord">
    </a>
</h4>

- [Overview](#overview)
- [Environment Variables](#environment-variables)
- [Usage](#usage)
  - [Echo application example](#echo-application-example)
    - [Run](#run)
    - [Check](#check)
  - [Endpoints](#endpoints)
  - [Anthropic Messages to Chat Completions translator](#anthropic-messages-to-chat-completions-translator)
- [Development](#development)
  - [Development Environment](#development-environment)
  - [Setup](#setup)
  - [IDE configuration](#ide-configuration)
  - [Lint](#lint)
  - [Test](#test)
  - [Git hooks](#git-hooks)
  - [Clean](#clean)
  - [Build](#build)
  - [Publish](#publish)

---

## Overview

Framework to create applications and model adapters for [AI DIAL](https://dialx.ai).

Applications and model adapters implemented using this framework will be compatible with [AI DIAL API](https://dialx.ai/dial_api) that was designed based on [Azure OpenAI API](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference).

---

## Environment Variables

|Variable|Default|Description|
|---|---|---|
|DIAL_SDK_HEADERS_TO_PROXY|``|A comma-separated list of headers that should be proxied from incoming requests to outgoing requests to the DIAL API. By default, no headers are proxied.|
|DIAL_SDK_SSE_HEARTBEAT_INTERVAL||When set, the SDK inserts ping comments into streaming chat completion responses after the response has been idle for the specified number of seconds, helping prevent read timeouts when the DIAL application isn't responsive.|
|PYDANTIC_V2|False|When `True` and Pydantic V2 is installed, DIAL SDK classes for requests/responses will be based on Pydantic V2 `BaseModel`. Otherwise, they will be based on Pydantic V1 `BaseModel`.|

Logging-related environment variables (log level, console format, and trace/span correlation) are documented in [docs/logging.md](docs/logging.md).

---

## Usage

Install the library using [pip](https://pip.pypa.io/en/stable/getting-started):

```sh
pip install aidial-sdk
```

### Echo application example

The echo application example replies to the user by repeating their last message:

```python
# Save this as app.py
import uvicorn

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


# ChatCompletion is an abstract class for applications and model adapters
class EchoApplication(ChatCompletion):
    async def chat_completion(self, request: Request, response: Response) -> None:
        # Get last message (the newest) from the history
        last_user_message = request.messages[-1]

        # Generate response with a single choice
        with response.create_single_choice() as choice:
            # Fill the content of the response with the last user's content
            choice.append_content(last_user_message.text())


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_chat_completion("echo", EchoApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
```

#### Run

```sh
python3 app.py
```

#### Check

Send the next request:

```sh
curl http://127.0.0.1:5000/openai/deployments/echo/chat/completions \
  -H "Content-Type: application/json" \
  -H "Api-Key: DIAL_API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Repeat me!"}]
  }'
```

You will see the JSON response as:

```json
{
    "choices":[
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": "Repeat me!"
            }
        }
    ],
    "usage": null,
    "id": "d08cfda2-d7c8-476f-8b95-424195fcdafe",
    "created": 1695298034,
    "object": "chat.completion"
}
```

---

### Endpoints

Every deployment is exposed under two base paths:

|Base path|Description|
|---|---|
|`/openai/deployments/{deployment_name}`|The DIAL API path. The deployment name is a part of the path.|
|`/openai/v1`|The Azure OpenAI v1 API path. The deployment name comes from the request headers.|

The following endpoints are served under each of them:

- `POST <base path>/chat/completions`
- `POST <base path>/rate`
- `POST <base path>/tokenize`
- `POST <base path>/truncate_prompt`
- `GET <base path>/configuration`
- `POST <base path>/embeddings`

`request.deployment_id` is resolved from the first of the following sources that is set:

1. the `X-DIAL-OVERRIDE-NAME` header,
2. the deployment name from the path, for the `/openai/deployments/{deployment_name}` requests,
3. the `X-DIAL-DEPLOYMENT-ID` header, which DIAL Core sets when it calls the `/openai/v1` endpoints.

An `/openai/v1` request with none of the headers set fails with `500 Internal Server Error`.

---

### Anthropic Messages to Chat Completions translator

The translator lets an Anthropic-native client (e.g. Claude Code) talk to a model that only speaks the [Chat Completions API](https://platform.openai.com/docs/api-reference/chat). It converts an Anthropic Messages request into a Chat Completions request to DIAL Core at `DIAL_URL`, and converts the response, streaming or not, back into the Anthropic Messages shape.

The translator requires the `translators` extra and Pydantic V2 models (`PYDANTIC_V2=True`):

```sh
pip install "aidial-sdk[translators]"
```

Mount it on your application:

```python
import httpx

from aidial_sdk import DIALApp
from aidial_sdk.translators.messages_to_chat_completions import mount_translator

app = DIALApp()
mount_translator(app, httpx.AsyncClient())
```

The second argument is the HTTP client the translator calls DIAL Core with: either an `httpx.AsyncClient` or an async function that takes the incoming `Request` and returns one. The `path` (`/openaiChatCompletions` by default) and `name` keyword arguments configure the mount.

|Endpoint|Calls on DIAL Core|
|---|---|
|`POST /openaiChatCompletions/anthropic/v1/messages`|`POST {DIAL_URL}/openai/v1/chat/completions`|
|`POST /openaiChatCompletions/legacy/anthropic/v1/messages`|`POST {DIAL_URL}/openai/deployments/{deployment}/chat/completions`|

`DIAL_URL` must be set, otherwise the endpoints answer `500`.

To expose a Chat Completions model under `/anthropic/v1/messages`, add an `anthropicMessages` interface to its DIAL Core config, pointing `base_url` at the mount path of the application that runs the translator (or at `/openaiChatCompletions/legacy` to call DIAL Core's legacy per-deployment endpoint):

<details>
<summary>DIAL Core config example</summary>

```json
{
  "models": {
    "gpt-5.5": {
      "type": "chat",
      "interfaces": {
        "openaiChatCompletions": {
          "base_url": "${OPENAI_ADAPTER_ORIGIN}"
        },
        "anthropicMessages": {
          "base_url": "${TRANSLATOR_ORIGIN}/openaiChatCompletions"
        }
      },
      "upstreams": [
        {
          "endpoint": "https://api.openai.com/v1/chat/completions",
          "key": "..."
        }
      ]
    }
  }
}
```

</details>

See the [translation guide](docs/messages-to-chat-translation.md) for how request parameters, content blocks, tools, caching, usage, and errors are translated, and for the translator's limitations.

---

## Development

### Development Environment

This project requires [Python ≥3.11](https://www.python.org/downloads/) and [Poetry ≥2.1.1](https://python-poetry.org/) for dependency management.

### Setup

1. Install Poetry. See the official [installation guide](https://python-poetry.org/docs/#installation).

2. *(Optional)* Specify custom Python or Poetry executables in `.env.dev`. This is useful if multiple versions are installed. By default, `python` and `poetry` are used.

   ```sh
   POETRY_PYTHON=path-to-python-exe
   POETRY=path-to-poetry-exe
   ```

3. Create and activate the virtual environment:

   ```sh
   make init_env
   source .venv/bin/activate
   ```

4. Install project dependencies (including linting, formatting, and test tools):

   ```sh
   make install
   ```

### IDE configuration

The recommended IDE is [VSCode](https://code.visualstudio.com/).
Open the project in VSCode and install the recommended extensions.
VS Code is configured to use the [Ruff formatter](https://docs.astral.sh/ruff/formatter/).

Alternatively you can use [PyCharm](https://www.jetbrains.com/pycharm/) that has built-in [Ruff support](https://www.jetbrains.com/help/pycharm/lsp-tools.html#ruff).

### Lint

Run the linting before committing:

```sh
make lint
```

To auto-fix formatting issues run:

```sh
make format
```

### Test

Run unit tests locally for available python versions:

```sh
make test
```

Run unit tests for the specific python version:

```sh
make test PYTHON=3.11
```

### Git hooks

You may optionally install Git hooks that will automatically run the linting step on Git push. You only need to do it once for the given repository.

```sh
make install_git_hooks
```

> [!IMPORTANT]
> This command doesn't work if you have already installed Git hooks locally or globally.

### Clean

To remove the virtual environment and build artifacts run:

```sh
make clean
```

### Build

To build the package run:

```sh
make build
```

### Publish

To publish the package to PyPI run:

```sh
make publish
```

---
