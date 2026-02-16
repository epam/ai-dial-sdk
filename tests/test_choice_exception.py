from aidial_sdk import HTTPException as DIALException
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from tests.utils.chunks import check_sse_stream, create_single_choice_chunk
from tests.utils.client import create_app_client


class ChoiceExceptionApplication(ChatCompletion):
    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        response.set_response_id("test_id")
        response.set_created(0)

        with response.create_single_choice() as choice:
            choice.append_content("Partial content")
            await response.aflush()
            raise DIALException("Something went wrong!", 500)


def test_choice_not_closed_on_exception():
    client = create_app_client(ChoiceExceptionApplication())

    response = client.post(
        "chat/completions",
        json={
            "messages": [{"role": "user", "content": "test"}],
            "stream": True,
        },
    )

    # Expected stream should NOT contain an EndChoiceChunk (finish_reason)
    # because the exception occurred before the choice was properly closed.
    expected_stream = [
        create_single_choice_chunk(delta={"role": "assistant"}),
        create_single_choice_chunk(delta={"content": "Partial content"}),
        {
            "error": {
                "message": "Something went wrong!",
                "type": "runtime_error",
                "code": "500",
            }
        },
    ]

    check_sse_stream(response.iter_lines(), expected_stream)
