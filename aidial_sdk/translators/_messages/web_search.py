import uuid

from anthropic.types import ServerToolUseBlock, WebSearchToolResultBlock
from anthropic.types.content_block import ContentBlock as AnthropicContentBlock
from anthropic.types.web_search_result_block import WebSearchResultBlock


def to_anthropic_web_search_blocks(
    citations: list[tuple[str, str]],
) -> list[AnthropicContentBlock]:
    if not citations:
        return []
    tool_use_id = f"srvtoolu_{uuid.uuid4().hex}"
    return [
        ServerToolUseBlock(
            type="server_tool_use",
            id=tool_use_id,
            name="web_search",
            input={"query": ""},
        ),
        WebSearchToolResultBlock(
            type="web_search_tool_result",
            tool_use_id=tool_use_id,
            content=[
                WebSearchResultBlock(
                    type="web_search_result",
                    url=url,
                    title=title,
                    encrypted_content="",
                )
                for url, title in citations
            ],
        ),
    ]
