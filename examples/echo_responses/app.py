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
        # Get last message (the newest) from the history and it's text
        last_message = request.messages[-1].text()

        # Generate a single output message
        with response.create_message() as message:
            message.append_text(last_message)


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_responses("echo", EchoApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
