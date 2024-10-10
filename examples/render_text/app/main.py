"""
A simple text-to-image DIAL application.
Takes the last message, rasterizes the text and
sends the image back to the user in an attachment.
"""

import os

import uvicorn

from aidial_sdk import DIALApp
from aidial_sdk import HTTPException as DIALException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response

from .image import text_to_image_base64, upload_png_image

DIAL_URL = os.environ.get("DIAL_URL")


# ChatCompletion is an abstract class for applications and model adapters
class RenderTextApplication(ChatCompletion):
    async def chat_completion(self, request: Request, response: Response):
        # Create a single choice
        with response.create_single_choice() as choice:
            # Get the last message content
            content = request.messages[-1].text()

            # The image may be returned either as base64 string or as URL
            # The content specifies the mode of return: 'base64' or 'url'
            try:
                command, text = content.split(",", 1)
                if command not in ["base64", "url"]:
                    raise DIALException(
                        message="The command must be either 'base64' or 'url'",
                        status_code=422,
                    )
            except ValueError:
                raise DIALException(
                    message="The content must be in the format '(base64|url),<text>'",
                    status_code=422,
                )

            # Rasterize the user message to an image
            image_base64 = text_to_image_base64(text)
            image_type = "image/png"

            # Add the image as an attachment
            if command == "base64":
                # As base64 string
                choice.add_attachment(
                    type=image_type, title="Image", data=image_base64
                )
            else:
                # As URL to DIAL File storage
                if DIAL_URL is None:
                    # DIAL SDK automatically converts standard Python exceptions to 500 Internal Server Error
                    raise ValueError("DIAL_URL environment variable is unset")

                # Upload the image to DIAL File storage
                image_url = await upload_png_image(
                    DIAL_URL, "images/picture.png", image_base64
                )

                # And return as an attachment
                choice.add_attachment(
                    type=image_type, title="Image", url=image_url
                )

            # Return the image in Markdown format
            choice.append_content(
                f"![Image](data:{image_type};base64,{image_base64})"
            )


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp(
    dial_url=DIAL_URL,
    propagate_auth_headers=DIAL_URL is not None,
    add_healthcheck=True,
)

app.add_chat_completion("render-text", RenderTextApplication())

if __name__ == "__main__":
    uvicorn.run(app, port=5000)
