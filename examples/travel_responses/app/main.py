"""
A DIAL application which plans a trip over the OpenAI Responses API.

It shows what an agent built on `aidial_sdk.responses` looks like: reasoning,
a commentary message, parallel calls of a client-side function tool, the
server-side web search and image generation tools, a cited final answer,
a refusal, truncation by `max_output_tokens` and usage.

The model behind it is scripted (see `model.py`), so that it runs offline.
"""

from aidial_sdk import DIALApp
from aidial_sdk.exceptions import InvalidRequestError
from aidial_sdk.responses import (
    IncompleteReason,
    Request,
    Response,
    Responses,
)

from . import model, tools
from .model import SIGHTS, Sight, Thought


async def reason(request: Request, response: Response, thought: Thought) -> int:
    """Streams a reasoning item and returns its token count."""
    tokens = 0
    with response.create_reasoning() as reasoning:
        # A summary is only given when the client asks for one
        if request.reasoning is not None and request.reasoning.summary:
            reasoning.append_summary(thought.summary)

        with reasoning.create_text() as text:
            async for token in model.stream_tokens(thought.text):
                text.append(token)
                tokens += 1

        if "reasoning.encrypted_content" in (request.include or []):
            # A real model returns an opaque blob the client sends back as is
            reasoning.set_encrypted_content(model.encrypt(thought.text))

    return tokens


# Responses is an abstract class for applications and model adapters
class TravelApplication(Responses):
    async def create_response(
        self, request: Request, response: Response
    ) -> None:
        question = (
            request.user_messages[-1].text() if request.user_messages else ""
        )
        if not question.strip():
            # Raised before any event: an HTTP error, no stream is opened
            raise InvalidRequestError("Ask about a trip, e.g. 'Paris and Rome'")

        if model.is_refused(question):
            response.append_refusal(
                "I can't book trips or take payments, "
                "but I'm glad to help you plan one."
            )
            return

        cities = model.find_cities(question)
        if not cities:
            response.append_text(
                f"I know {', '.join(SIGHTS)}. Where are you going?"
            )
            return

        forecasts = tools.forecasts(request)
        pending = [city for city in cities if city not in forecasts]

        if pending and tools.can_call(request, tools.WEATHER_TOOL):
            await self.call_weather(request, response, pending)
        else:
            await self.answer(request, response, question, cities, forecasts)

    async def call_weather(
        self, request: Request, response: Response, cities: list[str]
    ) -> None:
        """Asks the client for the forecasts, ending the turn."""
        if request.parallel_tool_calls is False:
            cities = cities[:1]
        names = " and ".join(cities)

        thought = model.think_about_weather(names, tools.WEATHER_TOOL)
        reasoning_tokens = await reason(request, response, thought)
        output_tokens = reasoning_tokens

        with response.create_message(phase="commentary") as message:
            async for token in model.stream_tokens(
                f"Checking the weather in {names}."
            ):
                message.append_text(token)
                output_tokens += 1

        # Builders outlive a `with` block, so the calls stream side by side
        calls = [
            response.create_function_call(tools.WEATHER_TOOL) for _ in cities
        ]
        for call in calls:
            call.append_arguments('{"city": ')
        await model.work()
        for call, city in zip(calls, cities, strict=True):
            call.append_arguments(f'"{city}"}}')
        for call in calls:
            call.close()
        output_tokens += 2 * len(calls)

        response.set_usage(
            input_tokens=sum(
                model.count_tokens(message.text())
                for message in request.messages
            ),
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        )

    async def answer(
        self,
        request: Request,
        response: Response,
        question: str,
        cities: list[str],
        forecasts: dict[str, str],
    ) -> None:
        names = " and ".join(cities)
        reasoning_tokens = await reason(
            request, response, model.think_about_brief(names)
        )
        output_tokens = reasoning_tokens

        # A server-side tool: only used when the client enables it
        sights: dict[str, Sight] = {}
        if tools.has_tool(request, "web_search"):
            with response.create_web_search() as search:
                search.searching(query=f"must-see sights in {names}")
                await model.work()
                for city in cities:
                    search.add_source(SIGHTS[city].url)
            sights = {city: SIGHTS[city] for city in cities}

        tokens_left = request.max_output_tokens
        truncated = False
        written = ""
        with (
            response.create_message(phase="final_answer") as message,
            message.create_text() as text,
        ):
            for segment, sight in model.write_brief(cities, forecasts, sights):
                start = len(written)
                async for token in model.stream_tokens(segment):
                    if tokens_left == 0:
                        truncated = True
                        break
                    text.append(token)
                    written += token
                    output_tokens += 1
                    if tokens_left is not None:
                        tokens_left -= 1

                if truncated:
                    # Out of `max_output_tokens`: the answer stops short
                    message.set_incomplete()
                    response.set_incomplete(IncompleteReason.MAX_OUTPUT_TOKENS)
                    break

                if sight is not None:
                    text.add_url_citation(
                        sight.url,
                        title=sight.title,
                        start_index=start,
                        end_index=len(written),
                    )

        # A server-side tool too, with partial images while it generates
        if (
            not truncated
            and model.wants_postcard(question)
            and tools.has_tool(request, "image_generation")
        ):
            with response.create_image_generation() as image:
                image.generating()
                for _ in range(2):
                    await model.work()
                    image.append_partial(model.POSTCARD_PNG)
                image.set_result(model.POSTCARD_PNG)

        response.set_usage(
            input_tokens=sum(
                model.count_tokens(message.text())
                for message in request.messages
            ),
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        )


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_responses("travel", TravelApplication())
