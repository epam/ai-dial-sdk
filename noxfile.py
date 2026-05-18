from enum import Enum

import nox

nox.options.reuse_existing_virtualenvs = True

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


class UsePydanticV2(Enum):
    YES = "1"
    NO = "0"


@nox.session(python=["3.10", "3.11", "3.12", "3.13", "3.14"])
# Testing against earliest and latest supported versions of the dependencies
@nox.parametrize(
    "pydantic_info",
    [
        ("1.10.17", UsePydanticV2.NO, False),
        ("2.8.2", UsePydanticV2.NO, False),
        ("2.8.2", UsePydanticV2.YES, False),
        # Python 3.14 is supported since Pydantic v2.12
        ("2.13.1", UsePydanticV2.NO, True),
        ("2.13.1", UsePydanticV2.YES, True),
    ],
)
@nox.parametrize("httpx_version", ["0.25.0", "0.27.0"])
def test(
    session: nox.Session,
    pydantic_info: tuple[str, UsePydanticV2, bool],
    httpx_version: str,
) -> None:
    """Runs tests"""
    pydantic_version, use_pydantic_v2, python_314_supported = pydantic_info

    if session.python == "3.14":
        if not python_314_supported:
            session.skip("Python 3.14 is supported since Pydantic v2.12")
        if httpx_version == "0.25.0":
            session.skip("Earlier versions of httpx do not support Python 3.14")

    session.run("poetry", "install", external=True)
    session.install(f"pydantic=={pydantic_version}", f"httpx=={httpx_version}")
    session.run(
        "pytest",
        *session.posargs,
        env={"PYDANTIC_V2": str(use_pydantic_v2.value)},
    )
