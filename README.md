# AI DIAL Python SDK

## Overview

Framework to create applications and model adapters for [AI DIAL](https://epam-rail.com).

DIAL applications and model adapters should implement [AI DIAL API](https://epam-rail.com/dial_api), that was designed based on Azure OpenAI Chat Completion and Embedding API. This allows us to be compatible with clients already use the Azure OpenAI API.

## Usage

Install the library using `pip install aidial-sdk`

The echo application example that replies to the user with his last message:

```python
import uvicorn

from aidial_sdk import (
    ChatCompletion,
    ChatCompletionRequest,
    ChatCompletionResponse,
    DIALApp,
)

# ChatCompletion is an abstract class for applications
class EchoApplication(ChatCompletion):
    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        response: ChatCompletionResponse
    ) -> None:
        last_user_message = request.messages[-1]

        # Most often, applications don't need to support more than one response choice
        with response.create_single_choice() as choice:
            # fill content of the response with the last message
            choice.append_content(last_user_message.content)

# DIALApp extends FastAPI to provide an user-friendly interface for rounting requests to your applications
app = DIALApp()

# The application will be allowed on /openai/deployments/echo/chat/completions
app.add_chat_completion("echo", EchoApplication())

if __name__ == "__main__":
    # Run builded app on http://localhost:5000
    uvicorn.run(app, port=5000)
```

## Configuration

TODO

## Developer environment

This project uses [Python>=3.8](https://www.python.org/downloads/) and [Poetry==1.6.1](https://python-poetry.org/) as a dependency manager.

Check out Poetry's [documentation on how to install it](https://python-poetry.org/docs/#installation) on your system before proceeding.

### IDE configuration

The recommended IDE is [VSCode](https://code.visualstudio.com/).
Open the project in VSCode and install the recommended extensions.

The VSCode is configured to use PEP-8 compatible formatter [Black](https://black.readthedocs.io/en/stable/index.html).

Alternatively you can use [PyCharm](https://www.jetbrains.com/pycharm/).

Set-up the Black formatter for PyCharm [manually](https://black.readthedocs.io/en/stable/integrations/editors.html#pycharm-intellij-idea) or
install PyCharm>=2023.2 with [built-in Black support](https://blog.jetbrains.com/pycharm/2023/07/2023-2/#black).

### Install dependencies

To install the package dependencies and create a virtual environment run:

```sh
make install
```

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

Run unit tests locally for availiable python versions:

```sh
make test
```

Run unit tests for the specific python version:

```sh
make test PYTHON=3.8
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
