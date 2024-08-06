import nox

nox.options.reuse_existing_virtualenvs = True

SRC = "."


def format_with_args(session: nox.Session, *args):
    session.run("autoflake", *args)
    session.run("isort", *args)
    session.run("black", *args)


@nox.session
def lint(session: nox.Session):
    """Runs linters and fixers"""
    try:
        session.run("poetry", "install", "--all-extras", external=True)
        session.run("poetry", "check", "--lock", external=True)
        session.run("pyright", SRC)
        session.run("flake8", SRC)
        format_with_args(session, SRC, "--check")
    except Exception:
        session.error(
            "linting has failed. Run 'make format' to fix formatting and fix other errors manually"
        )


@nox.session
def format(session: nox.Session):
    """Runs linters and fixers"""
    session.run("poetry", "install", external=True)
    format_with_args(session, SRC)


@nox.session(python=["3.8", "3.9", "3.10", "3.11", "3.12"])
# Testing against earliest and latest supported versions of the dependencies
@nox.parametrize("pydantic", ["1.10.17", "2.8.2"])
@nox.parametrize("httpx", ["0.25.0", "0.27.0"])
def test(session: nox.Session, pydantic: str, httpx: str) -> None:
    """Runs tests"""
    session.run("poetry", "install", external=True)
    session.install(f"pydantic=={pydantic}")
    session.install(f"httpx=={httpx}")
    session.run("pytest")
