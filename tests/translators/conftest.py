from aidial_sdk._pydantic import PYDANTIC_V2

# The translator refuses to import without Pydantic v2
collect_ignore = [] if PYDANTIC_V2 else ["messages_to_chat_completions"]
