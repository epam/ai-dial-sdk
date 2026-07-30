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


_PYDANTIC_DEPS: dict[str, tuple[str, str]] = {
    "1.10.17": ("fastapi==0.125.0", "starlette==0.49.1"),
    "2.8.2": ("fastapi==0.135.1", "starlette==1.3.1"),
    "2.13.1": ("fastapi==0.135.1", "starlette==1.3.1"),
}


class UsePydanticV2(Enum):
    YES = "1"
    NO = "0"


# Testing against earliest and latest supported versions of the dependencies
_PYTHONS = ["3.10", "3.11", "3.12", "3.13"]

_PYDANTICS = [
    ("1.10.17", UsePydanticV2.NO),
    ("2.8.2", UsePydanticV2.NO),
    ("2.8.2", UsePydanticV2.YES),
    ("2.13.1", UsePydanticV2.NO),
    ("2.13.1", UsePydanticV2.YES),
]


@nox.session(python=_PYTHONS)
@nox.parametrize("pydantic", _PYDANTICS)
@nox.parametrize("httpx", ["0.25.0", "0.27.0"])
def test(
    session: nox.Session, pydantic: tuple[str, UsePydanticV2], httpx: str
) -> None:
    """Runs tests"""
    session.run("poetry", "install", "--all-extras", external=True)
    session.install(f"pydantic=={pydantic[0]}", f"httpx=={httpx}")
    session.install(*_PYDANTIC_DEPS[pydantic[0]])
    session.run(
        "pytest", *session.posargs, env={"PYDANTIC_V2": str(pydantic[1].value)}
    )


_TELEMETRY_TESTS = [
    "tests/test_telemetry_logs.py",
    "tests/test_log_config.py",
    "tests/test_configure_root_logger.py",
    "tests/test_json_log_formatter.py",
]

# The instrumentation packages (0.XXbY) are released in lockstep with
# the core packages (1.XX.Y) - both have to be pinned together.
_OTEL_CORE_VERSION = {
    "0.60b1": "1.39.1",
    "0.61b0": "1.40.0",
    "0.65b0": "1.44.0",
}

_OTEL_INSTRUMENTATIONS = [
    "aiohttp-client",
    "fastapi",
    "httpx",
    "logging",
    "requests",
    "system-metrics",
    "urllib",
]

_OTEL_CORE = ["sdk", "api", "exporter-otlp-proto-grpc"]


@nox.session(python=_PYTHONS)
@nox.parametrize("pydantic", _PYDANTICS)
@nox.parametrize("otel", list(_OTEL_CORE_VERSION))
def test_telemetry(
    session: nox.Session, pydantic: tuple[str, UsePydanticV2], otel: str
) -> None:
    """Runs telemetry (and logging) tests over the matrix of OTEL versions"""
    core = _OTEL_CORE_VERSION[otel]
    session.run("poetry", "install", "--all-extras", external=True)
    session.install(f"pydantic=={pydantic[0]}", *_PYDANTIC_DEPS[pydantic[0]])
    session.install(
        f"opentelemetry-exporter-prometheus=={otel}",
        *(
            f"opentelemetry-instrumentation-{n}=={otel}"
            for n in _OTEL_INSTRUMENTATIONS
        ),
        *(f"opentelemetry-{n}=={core}" for n in _OTEL_CORE),
    )
    session.run(
        "pytest",
        *_TELEMETRY_TESTS,
        *session.posargs,
        env={"PYDANTIC_V2": str(pydantic[1].value)},
    )
