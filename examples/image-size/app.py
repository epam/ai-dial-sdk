"""
A simple image-to-text DIAL application.
Takes the last message, extract an image from an attachment and
returns its width and height as text.
"""

import uvicorn
from image import get_image_base64_dimensions

from aidial_sdk import DIALApp
from aidial_sdk import HTTPException as DIALException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


# ChatCompletion is an abstract class for applications and model adapters
class ImageSizeApplication(ChatCompletion):
    async def chat_completion(self, request: Request, response: Response):
        # Create a single choice
        with response.create_single_choice() as choice:
            # Get the image from the last message attachments
            try:
                image = request.messages[-1].custom_content.attachments[0].data  # type: ignore
            except Exception:
                # Raise an exception if no image was found
                raise DIALException(
                    message="No image attachment was found in the last message",
                    status_code=422,
                )
            # Compute the dimensions
            (w, h) = get_image_base64_dimensions(image)
            # Return the dimensions as result
            choice.append_content(f"Dimensions: {w}x{h}px")


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_chat_completion("image-size", ImageSizeApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
