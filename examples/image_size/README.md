## Overview

An example of a simple image-to-text DIAL application.

It takes an image from the last user message attachments and returns back the image dimensions.

Upon start the Docker image exposes `openai/deployments/image-size/chat/completions` endpoint at port `5000`.

## Configuration

The application supports image attachments provided in one of the following format:

1. Base64 encoded image
2. URL to the image, which might be either
   * public URL or
   * URL pointing to a file in the DIAL file storage. `DIAL_URL` environment variable should be set to support image stored in the storage.

|Variable|Default|Description|
|---|---|---|
|DIAL_URL||URL of the core DIAL server. Optional. Used to access images stored in the DIAL file storage|

## Usage

Find how to integrate the application into the DIAL Core and call it using DIAL API in the [cookbook](https://github.com/epam/ai-dial/blob/main/dial-cookbook/examples/how_to_call_image_to_text_applications.ipynb).