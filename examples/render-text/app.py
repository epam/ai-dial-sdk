"""
A simple text-to-image DIAL application.
Takes the last message, rasterizes the text and
sends the image back to the user in an attachment.
"""

import uvicorn
from image import text_to_image_base64

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


# ChatCompletion is an abstract class for applications and model adapters
class RenderTextApplication(ChatCompletion):
    async def chat_completion(self, request: Request, response: Response):
        # Create a single choice
        with response.create_single_choice() as choice:
            # Get the last message content
            content = request.messages[-1].content or ""
            # Return the reversed content
            base64_image = text_to_image_base64(content)
            # Add the image as an attachment
            choice.add_attachment(
                type="image/png", title="Image", data=base64_image
            )
            # Return the image generation status as a completion
            choice.append_content("Image was generated successfully")


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_chat_completion("render-text", RenderTextApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
