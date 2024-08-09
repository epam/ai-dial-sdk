## Overview

An example of a simple text-to-image DIAL application.

It takes a text from the last user message attachments and returns back the image with the rasterized text.

The generated image is added as an image attachment to the response message and also as a Markdown image in the response text.

Upon start the Docker image exposes `openai/deployments/render-text/chat/completions` endpoint at port `5000`.

## Configuration

The application returns the image in one of the following formats:

1. Base64 encoded image
2. URL to the image stored in the DIAL file storage. `DIAL_URL` environment variable should be set to support image uploading to the storage.

The format of the image attachment is controlled by the user message, which is expected to have the following format: `(base64|url),<text to render>`.

|Variable|Default|Description|
|---|---|---|
|DIAL_URL||URL of the core DIAL server. Optional. Used to upload generated images the DIAL file storage|

## Usage

Find how to integrate the application into the DIAL Core and call it using DIAL API in the [cookbook](https://github.com/epam/ai-dial/blob/main/dial-cookbook/examples/how_to_call_text_to_image_applications.ipynb).