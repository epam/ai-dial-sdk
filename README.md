# AI DIAL Python SDK

## Overview

Framework to create applications and model adapters for [AI DIAL](https://epam-rail.com).

Applications and model adapters implemented using this framework will be compatible with [AI DIAL API](https://epam-rail.com/dial_api) that was designed based on [Azure OpenAI API](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference).

## Usage

Install the library using [pip](https://pip.pypa.io/en/stable/getting-started):

```
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
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        # Get last message (the newest) from the history
        last_user_message = request.messages[-1]

        # Generate response with a single choice
        with response.create_single_choice() as choice:
            # Fill the content of the response with the last user's content
            choice.append_content(last_user_message.content or "")


# DIALApp extends FastAPI to provide an user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_chat_completion("echo", EchoApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
```

#### Run
```
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

## Developer environment

This project uses [Python>=3.8](https://www.python.org/downloads/) and [Poetry>=1.6.1](https://python-poetry.org/) as a dependency manager.

Check out Poetry's [documentation on how to install it](https://python-poetry.org/docs/#installation) on your system before proceeding.

To install requirements:

```
poetry install
```

This will install all requirements for running the package, linting, formatting and tests.

### IDE configuration

The recommended IDE is [VSCode](https://code.visualstudio.com/).
Open the project in VSCode and install the recommended extensions.

The VSCode is configured to use PEP-8 compatible formatter [Black](https://black.readthedocs.io/en/stable/index.html).

Alternatively you can use [PyCharm](https://www.jetbrains.com/pycharm/).

Set-up the Black formatter for PyCharm [manually](https://black.readthedocs.io/en/stable/integrations/editors.html#pycharm-intellij-idea) or
install PyCharm>=2023.2 with [built-in Black support](https://blog.jetbrains.com/pycharm/2023/07/2023-2/#black).

## Lint

Run the linting before committing:

```sh
make lint
```

To auto-fix formatting issues run:

```sh
make format
```

## Test

Run unit tests locally for available python versions:

```sh
make test
```

Run unit tests for the specific python version:

```sh
make test PYTHON=3.11
```

## Clean

To remove the virtual environment and build artifacts run:

```sh
make clean
```

## Build

To build the package run:

```sh
make build
```

## Publish

To publish the package to PyPI run:

```sh
make publish
```
