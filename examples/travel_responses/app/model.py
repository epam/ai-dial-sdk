"""
A scripted stand-in for a language model, so that the example runs offline
and answers alike every time. A real application calls a model here.
Words stand in for tokens.
"""

import asyncio
import base64
import re
from collections.abc import AsyncIterator
from typing import NamedTuple


class Sight(NamedTuple):
    title: str
    url: str


class Thought(NamedTuple):
    summary: str
    text: str


# What the web search "finds", per city the model knows
SIGHTS = {
    "Paris": Sight("the Louvre", "https://en.wikipedia.org/wiki/Louvre"),
    "Rome": Sight("the Colosseum", "https://en.wikipedia.org/wiki/Colosseum"),
    "Kyiv": Sight(
        "the Kyiv Pechersk Lavra",
        "https://en.wikipedia.org/wiki/Kyiv_Pechersk_Lavra",
    ),
    "Tokyo": Sight("Sensō-ji", "https://en.wikipedia.org/wiki/Sens%C5%8D-ji"),
}

# A 1x1 PNG standing in for a generated postcard
POSTCARD_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA"
    "60e6kgAAAABJRU5ErkJggg=="
)

_REFUSED = re.compile(r"\b(book|pay)\b", re.IGNORECASE)

# The pause between two tokens, so that a streamed answer is seen streaming
_DELAY = 0.05


def count_tokens(text: str) -> int:
    return len(text.split())


async def stream_tokens(text: str) -> AsyncIterator[str]:
    """Yields `text` token by token, at the pace of a model."""
    for token in re.findall(r"\s*\S+\s*", text):
        await asyncio.sleep(_DELAY)
        yield token


async def work() -> None:
    """Waits as long as a model takes to produce one token."""
    await asyncio.sleep(_DELAY)


def encrypt(text: str) -> str:
    """Stands in for the opaque blob a model gives for its reasoning."""
    return base64.b64encode(text.encode()).decode()


def is_refused(question: str) -> bool:
    return _REFUSED.search(question) is not None


def find_cities(question: str) -> list[str]:
    """The cities the model knows, in the order the question names them."""
    lowered = question.lower()
    return sorted(
        (city for city in SIGHTS if city.lower() in lowered),
        key=lambda city: lowered.find(city.lower()),
    )


def wants_postcard(question: str) -> bool:
    return "postcard" in question.lower()


def think_about_weather(names: str, tool: str) -> Thought:
    return Thought(
        "Checking the weather first.",
        f"The user plans a trip to {names}. "
        f"I need the weather first, so I call {tool}.",
    )


def think_about_brief(names: str) -> Thought:
    return Thought(
        "Putting the trip brief together.",
        f"I have what I need about {names}. "
        "I look up one sight per city and write the brief.",
    )


def write_brief(
    cities: list[str], forecasts: dict[str, str], sights: dict[str, Sight]
) -> list[tuple[str, Sight | None]]:
    """The brief as segments of text, each cited one with its sight."""
    segments: list[tuple[str, Sight | None]] = [("Your trip brief:\n", None)]
    for city in cities:
        forecast = forecasts.get(city, "no forecast")
        segments.append((f"- {city}: {forecast}. ", None))
        if city in sights:
            sight = sights[city]
            segments += [("Don't miss ", None), (sight.title, sight)]
        segments.append((".\n" if city in sights else "\n", None))
    return segments
