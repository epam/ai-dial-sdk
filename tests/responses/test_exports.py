import aidial_sdk.responses

_EXPORTS = {
    # entry points
    "ResponsesApplication",
    "Request",
    "Response",
    # item / part builders
    "Message",
    "TextPart",
    "RefusalPart",
    "Reasoning",
    "SummaryPart",
    "ReasoningTextPart",
    "FunctionCall",
    "CustomToolCall",
    "WebSearch",
    "ImageGeneration",
    # enums
    "ItemStatus",
    "ResponseStatus",
    "IncompleteReason",
    "ErrorCode",
    "MessagePhase",
    # request models
    "InputMessage",
    "InputRole",
    "InputTextPart",
    "InputImagePart",
    "InputFilePart",
    "InputAudioPart",
    "OutputTextPart",
    "RefusalContentPart",
    "FunctionCallItem",
    "FunctionCallOutputItem",
    "CustomToolCallItem",
    "CustomToolCallOutputItem",
    "ReasoningInputItem",
    "ItemReference",
    "RawItem",
    "DeploymentContext",
    "Tool",
    "FunctionTool",
    "CustomTool",
    "ToolChoice",
    "TextConfig",
    "ReasoningConfig",
    "StreamOptions",
    # output-side value models
    "Annotation",
    "UrlCitation",
    "FileCitation",
    "ContainerFileCitation",
    "FilePath",
    "Logprob",
    "WebSearchAction",
}


def test_every_name_imports():
    for name in aidial_sdk.responses.__all__:
        # Raises when the name isn't there
        getattr(aidial_sdk.responses, name)


def test_all_is_sorted_without_duplicates():
    names = aidial_sdk.responses.__all__

    assert names == sorted(names)
    assert len(names) == len(set(names))


def test_all_is_exactly_the_public_surface():
    assert set(aidial_sdk.responses.__all__) == _EXPORTS


def test_message_is_the_output_builder():
    from aidial_sdk.responses import InputMessage, Message
    from aidial_sdk.responses.message import Message as MessageBuilder
    from aidial_sdk.responses.request import InputMessage as RequestMessage

    assert Message is MessageBuilder
    assert InputMessage is RequestMessage
