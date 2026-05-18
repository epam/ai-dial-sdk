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
    "pydantic",
    [
        ("1.10.17", UsePydanticV2.NO),
        ("2.8.2", UsePydanticV2.NO),
        ("2.8.2", UsePydanticV2.YES),
        ("2.13.1", UsePydanticV2.NO),
        ("2.13.1", UsePydanticV2.YES),
    ],
)
@nox.parametrize("httpx", ["0.25.0", "0.27.0"])
def test(
    session: nox.Session, pydantic: tuple[str, UsePydanticV2], httpx: str
) -> None:
    """Runs tests"""
    session.run("poetry", "install", external=True)
    session.install(f"pydantic=={pydantic[0]}", f"httpx=={httpx}")
    session.run(
        "pytest", *session.posargs, env={"PYDANTIC_V2": str(pydantic[1].value)}
    )
