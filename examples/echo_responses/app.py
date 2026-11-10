"""
A DIAL application which returns back the text of the last input message
over the OpenAI Responses API.
"""

import uvicorn

from aidial_sdk import DIALApp
from aidial_sdk.responses import Request, Response, ResponsesApplication


# ResponsesApplication is an abstract class for Responses API applications
class EchoApplication(ResponsesApplication):
    async def create_response(
        self, request: Request, response: Response
    ) -> None:
        # Generate a single output message with the last input message's text
        with response.create_message() as message:
            message.append_text(request.messages[-1].text())


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_responses("echo", EchoApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
