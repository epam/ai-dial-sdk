import base64

import requests
import uvicorn

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response


class ImageEchoApplication(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        last_user_message = request.messages[-1]

        with response.create_single_choice() as choice:
            image_url = (last_user_message.content or "").strip()
            image_extension = image_url.split(".")[-1]

            try:
                image_bytes = requests.get(image_url).content
            except requests.exceptions.MissingSchema as e:
                choice.append_content(str(e))
                return

            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

            # Add content with the user image in base64
            choice.append_content(
                f"![Image](data:image/{image_extension};base64,{image_base64})"
            )

            # Add an attachment with the same user image, but using url
            choice.add_attachment(
                type=f"image/{image_extension}",
                url=image_url,
                title="Attachment Image",
            )


app = DIALApp()
app.add_chat_completion("image-echo", ImageEchoApplication())

if __name__ == "__main__":
    uvicorn.run(app, port=5001)
