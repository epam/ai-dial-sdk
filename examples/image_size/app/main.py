"""
A simple image-to-text DIAL application.
Takes the last message, extract an image from an attachment and
returns its width and height as text.
"""

import os
from urllib.parse import urlparse

from aidial_sdk import DIALApp
from aidial_sdk import HTTPException as DIALException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response

from .image import download_image_as_base64, get_image_base64_size

DIAL_URL = os.environ.get("DIAL_URL")


# A helper to distinguish relative URLs from absolute ones
# Relative URLs are treated as URLs to the DIAL File storage
# Absolute URLs are treated as publicly accessible URLs to external resources
def is_relative_url(url) -> bool:
    parsed_url = urlparse(url)
    return (
        not parsed_url.scheme
        and not parsed_url.netloc
        and not url.startswith("/")
    )


# ChatCompletion is an abstract class for applications and model adapters
class ImageSizeApplication(ChatCompletion):
    async def chat_completion(self, request: Request, response: Response):
        # Create a single choice
        with response.create_single_choice() as choice:
            if (
                request.messages[-1].custom_content is None
                or request.messages[-1].custom_content.attachments is None
            ):
                # Raise an exception if no image was found
                raise DIALException(
                    message="No image attachment was found in the last message",
                    status_code=422,
                )

            # Get the image from the last message attachments
            attachment = request.messages[-1].custom_content.attachments[0]

            # The attachment contains either the image content as base64 string or the image URL
            if attachment.data is not None:
                image_data = attachment.data
            else:
                image_url = attachment.url
                assert image_url is not None, "Image URL is not found"

                # Download the image from the URL
                if is_relative_url(image_url):
                    if DIAL_URL is None:
                        raise Exception(
                            "DIAL_URL environment variable is not set"
                        )
                    image_abs_url = f"{DIAL_URL}/v1/{image_url}"
                else:
                    image_abs_url = image_url

                image_data = download_image_as_base64(image_abs_url)

            # Compute the image size
            (w, h) = get_image_base64_size(image_data)

            # Return the image size
            choice.append_content(f"Size: {w}x{h}px")


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp(
    dial_url=DIAL_URL,
    propagation_auth_headers=DIAL_URL is not None,
    add_healthcheck=True,
)

app.add_chat_completion("image-size", ImageSizeApplication())
