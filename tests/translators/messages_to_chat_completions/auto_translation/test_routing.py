from unittest.mock import ANY

import anthropic
import pytest
from anthropic.types import TextBlock

from aidial_sdk import DIALApp
from aidial_sdk.deployment._headers import DIAL_OVERRIDE_NAME
from tests.translators.messages_to_chat_completions.auto_translation.helpers import (
    AppClient,
    replying,
)

_NOT_FOUND = {
    "type": "error",
    "error": {"type": "not_found_error", "message": ANY},
}


async def test_the_deployment_from_the_header_serves_the_request(stream: bool):
    foo = replying("Hi from foo")
    app = DIALApp().add_chat_completion(
        "foo", foo, expose_as_anthropic_messages=True
    )

    async with AppClient(app).with_deployment("foo").anthropic() as client:
        message = await client.final_message(stream=stream)

    assert message.model == "foo"
    assert message.content == [TextBlock(type="text", text="Hi from foo")]
    assert [request.deployment_id for request in foo.requests] == ["foo"]


async def test_the_override_name_chooses_the_impl_but_not_the_model(
    stream: bool,
):
    foo = replying("Hi from foo")
    app = DIALApp().add_chat_completion(
        "foo", foo, expose_as_anthropic_messages=True
    )

    async with AppClient(app).with_deployment("bar").anthropic() as client:
        message = await client.final_message(
            stream=stream, extra_headers={DIAL_OVERRIDE_NAME: "foo"}
        )

    assert message.model == "bar"
    assert message.content == [TextBlock(type="text", text="Hi from foo")]
    assert [request.deployment_id for request in foo.requests] == ["foo"]


async def test_an_unknown_deployment_is_not_found(stream: bool):
    foo = replying("Hi from foo")
    app = DIALApp().add_chat_completion(
        "foo", foo, expose_as_anthropic_messages=True
    )

    async with AppClient(app).with_deployment("bar").anthropic() as client:
        with pytest.raises(anthropic.NotFoundError) as exc:
            await client.final_message(stream=stream)

    assert exc.value.body == _NOT_FOUND
    assert foo.requests == []


async def test_each_deployment_is_served_by_its_own_impl(stream: bool):
    foo, bar = replying("Hi from foo"), replying("Hi from bar")
    app = (
        DIALApp()
        .add_chat_completion("foo", foo, expose_as_anthropic_messages=True)
        .add_chat_completion("bar", bar, expose_as_anthropic_messages=True)
    )

    client = AppClient(app)
    async with client.with_deployment("foo").anthropic() as c:
        foo_message = await c.final_message(stream=stream)
    async with client.with_deployment("bar").anthropic() as c:
        bar_message = await c.final_message(stream=stream)

    assert foo_message.content == [TextBlock(type="text", text="Hi from foo")]
    assert bar_message.content == [TextBlock(type="text", text="Hi from bar")]
    assert len(foo.requests) == len(bar.requests) == 1


async def test_the_model_field_does_not_choose_the_deployment(
    stream: bool,
):
    foo, bar = replying("Hi from foo"), replying("Hi from bar")
    app = (
        DIALApp()
        .add_chat_completion("foo", foo, expose_as_anthropic_messages=True)
        .add_chat_completion("bar", bar, expose_as_anthropic_messages=True)
    )

    async with AppClient(app).with_deployment("foo").anthropic() as client:
        message = await client.final_message(stream=stream, model="bar")

    assert message.model == "foo"
    assert message.content == [TextBlock(type="text", text="Hi from foo")]
    assert bar.requests == []


async def test_a_deployment_not_exposed_as_anthropic_messages_is_not_found(
    stream: bool,
):
    foo, bar = replying("Hi from foo"), replying("Hi from bar")
    app = (
        DIALApp()
        .add_chat_completion("foo", foo, expose_as_anthropic_messages=True)
        .add_chat_completion("bar", bar)
    )

    async with AppClient(app).with_deployment("bar").anthropic() as client:
        with pytest.raises(anthropic.NotFoundError) as exc:
            await client.final_message(stream=stream)

    assert exc.value.body == _NOT_FOUND
    assert bar.requests == []


async def test_the_endpoint_is_absent_unless_a_deployment_exposes_it(
    stream: bool,
):
    foo = replying("Hi from foo")
    app = DIALApp().add_chat_completion("foo", foo)

    async with AppClient(app).anthropic() as client:
        with pytest.raises(anthropic.NotFoundError):
            await client.final_message(stream=stream)

    assert foo.requests == []


async def test_a_request_without_the_deployment_id_is_rejected(
    stream: bool,
):
    foo = replying("Hi from foo")
    app = DIALApp().add_chat_completion(
        "foo", foo, expose_as_anthropic_messages=True
    )

    async with AppClient(app).with_deployment(None).anthropic() as client:
        with pytest.raises(anthropic.InternalServerError) as exc:
            await client.final_message(stream=stream)

    assert exc.value.body == {
        "type": "error",
        "error": {"type": "api_error", "message": ANY},
    }
    assert foo.requests == []


async def test_a_templated_deployment_receives_the_path_parameter(
    stream: bool,
):
    foo = replying("Hi from foo")
    app = DIALApp().add_chat_completion(
        "foo{id}bar", foo, expose_as_anthropic_messages=True
    )

    async with (
        AppClient(app).with_deployment("foo123bar").anthropic() as client
    ):
        message = await client.final_message(stream=stream)

    assert message.content == [TextBlock(type="text", text="Hi from foo")]
    assert [
        (request.deployment_id, request.original_request.path_params)
        for request in foo.requests
    ] == [("foo123bar", {"id": "123"})]


@pytest.mark.parametrize("deployment", ["foobar", "foo123baz", "bar"])
async def test_a_deployment_not_matching_the_template_is_not_found(
    stream: bool, deployment: str
):
    foo = replying("Hi from foo")
    app = DIALApp().add_chat_completion(
        "foo{id}bar", foo, expose_as_anthropic_messages=True
    )

    async with AppClient(app).with_deployment(deployment).anthropic() as client:
        with pytest.raises(anthropic.NotFoundError) as exc:
            await client.final_message(stream=stream)

    assert exc.value.body == _NOT_FOUND
    assert foo.requests == []


async def test_the_chat_completions_endpoints_are_still_served(stream: bool):
    foo = replying("Hi from foo")
    app = DIALApp().add_chat_completion(
        "foo", foo, expose_as_anthropic_messages=True
    )

    client = AppClient(app)
    async with client.legacy_openai() as c:
        legacy_completion = await c.final_message(stream=stream)
    async with client.openai() as c:
        v1_completion = await c.final_message(stream=stream)
    async with client.anthropic() as c:
        message = await c.final_message(stream=stream)

    for completion in (legacy_completion, v1_completion):
        assert completion.choices[0].message.content == "Hi from foo"
    assert message.content == [TextBlock(type="text", text="Hi from foo")]
    assert len(foo.requests) == 3
