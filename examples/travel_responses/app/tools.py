"""
The tool traffic of a request: the tools the client declared, and the
outputs it sent back for the calls of the previous turn.
"""

import json

from aidial_sdk.responses import (
    FunctionCallItem,
    FunctionCallOutputItem,
    FunctionTool,
    Request,
)

WEATHER_TOOL = "get_weather"


def has_tool(request: Request, tool_type: str) -> bool:
    """Whether a tool of the type, e.g. `web_search`, is enabled."""
    return any(tool.type == tool_type for tool in request.tools or [])


def can_call(request: Request, name: str) -> bool:
    """Whether the client declared the function and allows calling it."""
    return request.tool_choice != "none" and any(
        isinstance(tool, FunctionTool) and tool.name == name
        for tool in request.tools or []
    )


def forecasts(request: Request) -> dict[str, str]:
    """
    The forecasts the client sent back, per city: each `function_call_output`
    is paired by `call_id` with the `get_weather` call it answers.
    """
    calls = {
        item.call_id: item
        for item in request.input_items
        if isinstance(item, FunctionCallItem) and item.name == WEATHER_TOOL
    }
    return {
        json.loads(calls[item.call_id].arguments)["city"]: item.output
        for item in request.input_items
        if isinstance(item, FunctionCallOutputItem)
        and item.call_id in calls
        and isinstance(item.output, str)
    }
