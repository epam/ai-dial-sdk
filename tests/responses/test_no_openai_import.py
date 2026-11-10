"""
`openai` is the tests' conformance oracle and nothing more.
The SDK never imports it, and it is not a dependency of the package. The
one exception is `aidial_sdk.translators`: pydantic-v2-only and opt-in,
via the `translators` extra.
"""

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import aidial_sdk

_SDK = Path(aidial_sdk.__file__).parent
_TRANSLATORS = _SDK / "translators"
_PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


def _imports_openai(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            modules = [node.module or ""]
        else:
            continue
        if any(m == "openai" or m.startswith("openai.") for m in modules):
            return True
    return False


def test_no_module_of_the_sdk_imports_openai():
    # The whole package, not only `responses`: none of it but the translators
    modules = sorted(
        p for p in _SDK.rglob("*.py") if _TRANSLATORS not in p.parents
    )
    assert _SDK / "responses" / "response.py" in modules

    assert [
        str(p.relative_to(_SDK)) for p in modules if _imports_openai(p)
    ] == []


def test_importing_the_sdk_does_not_load_openai():
    # Catches what the walk above can't: an import made at run time
    code = (
        "import sys, aidial_sdk.responses; "
        "assert 'openai' not in sys.modules, 'openai was loaded'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603


def _name(requirement: str) -> str:
    return re.split(r"[\s(<>=!~;\[]", requirement, maxsplit=1)[0].lower()


def test_openai_is_not_a_dependency():
    project = tomllib.loads(_PYPROJECT.read_text())["project"]
    names = {_name(requirement) for requirement in project["dependencies"]}

    assert "pydantic" in names
    assert "openai" not in names

    extras = project.get("optional-dependencies", {})
    assert {
        extra
        for extra, requirements in extras.items()
        if "openai" in map(_name, requirements)
    } <= {"translators"}
