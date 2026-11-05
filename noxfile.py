from enum import Enum

import nox

nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = [
    "test_without_translators",
    "test_translators",
    "test_header_propagation",
]

SRC = ["aidial_sdk", "tests", "noxfile.py", "examples"]


@nox.session
def lint(session: nox.Session):
    """Runs linters and fixers"""
    try:
        session.run("poetry", "install", "--all-extras", external=True)
        session.run("poetry", "check", "--lock", "--strict", external=True)
        session.run("ruff", "check", *SRC)
        session.run("ruff", "format", "--check", *SRC)
        session.run("pyright", *SRC)
    except Exception:
        session.error(
            "linting has failed. Run 'make format' to fix formatting and fix other errors manually"
        )


@nox.session
def format(session: nox.Session):
    """Runs linters and fixers"""
    session.run("poetry", "install", "--only", "lint", external=True)
    session.run("ruff", "check", "--fix", *SRC)
    session.run("ruff", "format", *SRC)


_PYDANTIC_DEPS: dict[str, tuple[str, str]] = {
    "1.10.17": ("fastapi==0.125.0", "starlette==0.49.1"),
    "2.8.2": ("fastapi==0.135.1", "starlette==1.3.1"),
    "2.13.1": ("fastapi==0.135.1", "starlette==1.3.1"),
}


class UsePydanticV2(Enum):
    YES = "1"
    NO = "0"


_python_matrix = nox.session(python=["3.11", "3.12", "3.13"])

# Testing against earliest and latest supported versions of the dependencies
_PYDANTIC_MATRIX = [
    ("1.10.17", UsePydanticV2.NO),
    ("2.8.2", UsePydanticV2.NO),
    ("2.8.2", UsePydanticV2.YES),
    ("2.13.1", UsePydanticV2.NO),
    ("2.13.1", UsePydanticV2.YES),
]
_HTTPX_MATRIX = ["0.25.0", "0.27.0"]


def _run_tests(
    session: nox.Session,
    pydantic: tuple[str, UsePydanticV2],
    httpx: str,
    *,
    extras: list[str],
    pytest_args: list[str],
) -> None:
    session.run(
        "poetry", "install", *(f"--extras={e}" for e in extras), external=True
    )
    session.install(f"pydantic=={pydantic[0]}", f"httpx=={httpx}")
    session.install(*_PYDANTIC_DEPS[pydantic[0]])
    session.run(
        "pytest",
        *pytest_args,
        *session.posargs,
        env={"PYDANTIC_V2": str(pydantic[1].value)},
    )


@_python_matrix
@nox.parametrize("pydantic", _PYDANTIC_MATRIX)
@nox.parametrize("httpx", _HTTPX_MATRIX)
def test_without_translators(
    session: nox.Session, pydantic: tuple[str, UsePydanticV2], httpx: str
) -> None:
    """Runs all the tests but the translators', without the translators extra"""
    _run_tests(
        session,
        pydantic,
        httpx,
        extras=["telemetry", "httpx"],
        pytest_args=["--ignore=tests/translators"],
    )


@_python_matrix
# The translators require Pydantic v2
@nox.parametrize(
    "pydantic", [p for p in _PYDANTIC_MATRIX if p[1] is UsePydanticV2.YES]
)
@nox.parametrize("httpx", _HTTPX_MATRIX)
def test_translators(
    session: nox.Session, pydantic: tuple[str, UsePydanticV2], httpx: str
) -> None:
    """Runs the translators' tests with the translators extra only"""
    _run_tests(
        session,
        pydantic,
        httpx,
        extras=["translators"],
        pytest_args=["tests/translators"],
    )


@_python_matrix
@nox.parametrize("wrapt", ["1.17.3", "2.4.0"])
def test_header_propagation(session: nox.Session, wrapt: str) -> None:
    session.run("poetry", "install", "--all-extras", external=True)
    session.install(f"wrapt=={wrapt}")
    session.run("pytest", "tests/test_header_propagation.py", *session.posargs)
