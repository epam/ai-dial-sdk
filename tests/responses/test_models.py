from typing import Any, get_args

import pytest
from openai.types.responses import ResponseUsage
from openai.types.responses import response_function_web_search as openai_ws
from openai.types.responses import response_output_text as openai_text
from openai.types.responses.response_usage import (
    InputTokensDetails as OpenAIInputTokensDetails,
)
from openai.types.responses.response_usage import (
    OutputTokensDetails as OpenAIOutputTokensDetails,
)

from aidial_sdk._pydantic._compat import BaseModel
from aidial_sdk.responses.models import (
    Annotation,
    ContainerFileCitation,
    FileCitation,
    FilePath,
    FindInPageAction,
    InputTokensDetails,
    Logprob,
    LogprobTopLogprob,
    OpenPageAction,
    OutputTokensDetails,
    SearchAction,
    SearchSource,
    UrlCitation,
    Usage,
    WebSearchAction,
)

_TEXT = "a"
_top_logprob = LogprobTopLogprob(token=_TEXT, bytes=[97], logprob=-0.5)

# (SDK model instance, its openai counterpart)
_CASES: list[tuple[BaseModel, Any]] = [
    (
        UrlCitation(url="https://a.b", title="T", start_index=0, end_index=3),
        openai_text.AnnotationURLCitation,
    ),
    (
        FileCitation(file_id="f", filename="f.txt", index=0),
        openai_text.AnnotationFileCitation,
    ),
    (
        ContainerFileCitation(
            container_id="c",
            file_id="f",
            filename="f.txt",
            start_index=0,
            end_index=3,
        ),
        openai_text.AnnotationContainerFileCitation,
    ),
    (FilePath(file_id="f", index=0), openai_text.AnnotationFilePath),
    (_top_logprob, openai_text.LogprobTopLogprob),
    (
        Logprob(
            token=_TEXT, bytes=[97], logprob=-0.5, top_logprobs=[_top_logprob]
        ),
        openai_text.Logprob,
    ),
    (
        Logprob(token=_TEXT, bytes=[], logprob=-0.5, top_logprobs=[]),
        openai_text.Logprob,
    ),
    (SearchSource(url="https://a.b"), openai_ws.ActionSearchSource),
    (SearchAction(), openai_ws.ActionSearch),
    (
        SearchAction(
            query="q",
            queries=["q", "r"],
            sources=[SearchSource(url="https://a.b")],
        ),
        openai_ws.ActionSearch,
    ),
    (OpenPageAction(), openai_ws.ActionOpenPage),
    (OpenPageAction(url="https://a.b"), openai_ws.ActionOpenPage),
    (FindInPageAction(url="https://a.b", pattern="p"), openai_ws.ActionFind),
    (
        InputTokensDetails(cached_tokens=1, cache_write_tokens=2),
        OpenAIInputTokensDetails,
    ),
    (OutputTokensDetails(reasoning_tokens=3), OpenAIOutputTokensDetails),
    (
        Usage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            input_tokens_details=InputTokensDetails(
                cached_tokens=1, cache_write_tokens=2
            ),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=3),
        ),
        ResponseUsage,
    ),
]


def _field_names(model: Any) -> tuple[set[str], set[str]]:
    """Returns (all, required) field names of an openai model."""
    # `model_fields` is pydantic v2 only, `__fields__` is the v1 spelling
    if hasattr(model, "model_fields"):
        fields = model.model_fields
        return set(fields), {n for n, f in fields.items() if f.is_required()}
    fields = model.__fields__
    return set(fields), {n for n, f in fields.items() if f.required}


def _validate(model: Any, data: dict[str, Any]) -> None:
    if hasattr(model, "model_validate"):
        model.model_validate(data)
    else:
        model.parse_obj(data)


@pytest.mark.parametrize(
    "instance, openai_model",
    _CASES,
    ids=[f"{type(i).__name__}-{n}" for n, (i, _) in enumerate(_CASES)],
)
def test_matches_openai(instance: BaseModel, openai_model: Any):
    dump = instance.model_dump()

    # openai models allow extra fields, so a stray field would pass validation
    all_fields, required_fields = _field_names(openai_model)
    assert required_fields <= set(dump) <= all_fields

    _validate(openai_model, dump)


def _type_literals(members: tuple[Any, ...]) -> set[str]:
    """The `type` discriminator values of the members of a union."""
    return {
        value
        for member in members
        for value in get_args(member.__annotations__["type"])
    }


@pytest.mark.parametrize(
    "union, openai_union",
    [
        (Annotation, openai_text.Annotation),
        (WebSearchAction, openai_ws.Action),
    ],
    ids=["Annotation", "WebSearchAction"],
)
def test_union_members_match_openai(union: Any, openai_union: Any):
    # openai spells these `Annotated[Union[...], PropertyInfo(...)]`
    openai_members = get_args(get_args(openai_union)[0])
    assert _type_literals(get_args(union)) == _type_literals(openai_members)
