"""
A DIAL application which returns back the content and attachments
from the last user message.
"""

import uvicorn

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


# ChatCompletion is an abstract class for applications and model adapters
class EchoApplication(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        # Get last message (the newest) from the history
        last_message = request.messages[-1]

        # Generate response with a single choice
        with response.create_single_choice() as choice:
            # Fill the content of the response with the last user's content
            choice.append_content(last_message.text())

            if last_message.custom_content is not None:
                for attachment in last_message.custom_content.attachments or []:
                    # Add the same attachment to the response
                    choice.add_attachment(**attachment.dict())


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_chat_completion("echo", EchoApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
