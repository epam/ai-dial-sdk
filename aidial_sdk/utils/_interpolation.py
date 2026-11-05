"""Deployment names may be templates, e.g. "app-{idx}" or "app-{idx:int}",
in the same syntax Starlette uses for the path params."""

from collections.abc import Callable
from functools import cache
from re import Match
from typing import Any

from starlette.convertors import Convertor
from starlette.routing import compile_path


@cache
def _compile_path_template(
    name: str,
) -> tuple[Callable[[str], Match[str] | None], str, dict[str, Convertor[Any]]]:
    # compile_path reads a pattern with no leading slash as a *host* pattern,
    # which it truncates at ":", so the name is compiled as a path instead.
    regex, path_format, convertors = compile_path("/" + name)

    def matcher(deployment_id: str) -> Match[str] | None:
        return regex.match("/" + deployment_id)

    return matcher, path_format.removeprefix("/"), convertors


def match_deployment_id(
    template: str, deployment_id: str
) -> dict[str, Any] | None:
    """Matches a deployment id against a deployment name template
    (e.g. "app-{idx}"), returning the path params it resolves to,
    or None if the name isn't a template or doesn't match."""

    if "{" not in template:
        return None

    matcher, _path_format, convertors = _compile_path_template(template)

    if (match := matcher(deployment_id)) is None:
        return None

    return {
        key: convertors[key].convert(value)
        for key, value in match.groupdict().items()
    }


def interpolate_deployment_id(deployment_id: str, path_params: dict) -> str:
    """Fills a deployment name template (e.g. "app-{idx:int}") with the
    path params the request it came in on was routed by."""

    _matcher, path_format, convertors = _compile_path_template(deployment_id)

    # the format drops the convertor types, so "app-{idx:int}" -> "app-{idx}"
    return path_format.format(**path_params) if convertors else deployment_id
