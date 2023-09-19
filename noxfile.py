import nox

nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ["tests"]


@nox.session(python=["3.11"])
def tests(session: nox.Session) -> None:
    """Runs tests"""
    session.run("poetry", "install", external=True)
    session.run("pytest")
