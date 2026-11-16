"""
A DIAL application which returns back the text of the last input message
over the OpenAI Responses API.
"""

import uvicorn

from aidial_sdk import DIALApp
from aidial_sdk.responses import Request, Response, Responses


# Responses is an abstract class for applications and model adapters
class EchoApplication(Responses):
    async def create_response(
        self, request: Request, response: Response
    ) -> None:
        # Get the text of the last message (the newest), if there is one:
        # the input may hold no messages, e.g. only tool results
        messages = request.messages
        text = messages[-1].text() if messages else ""

        # Generate a single output message
        with response.create_message() as message:
            message.append_text(text)


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_responses("echo", EchoApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
