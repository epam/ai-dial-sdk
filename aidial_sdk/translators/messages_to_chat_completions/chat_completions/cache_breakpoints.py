import re
from datetime import UTC, datetime, timedelta

from anthropic.types.beta import BetaCacheControlEphemeralParam as CacheControl

from aidial_sdk.chat_completion.request import CacheBreakpoint
from aidial_sdk.utils.logging import logger as log

_TTL = re.compile(r"^([1-9]\d*)([mh])$")

_UNITS = {
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
}


def to_dial_cache_breakpoint(
    controls: list[CacheControl],
) -> CacheBreakpoint | None:
    if not controls:
        return None
    expires_at: str | None = None
    for control in controls:
        try:
            if (ttl := _ttl(control)) is not None:
                candidate = _expire_at(ttl)
                expires_at = (
                    max(expires_at, candidate) if expires_at else candidate
                )
        except (OverflowError, ValueError):
            log.warning(
                f"Ignoring unreadable cache_control.ttl: {control.get('ttl')}"
            )
    return CacheBreakpoint(expire_at=expires_at)


def _ttl(control: CacheControl) -> timedelta | None:
    raw = control.get("ttl")
    if raw is None:
        return None
    if isinstance(raw, str) and (match := _TTL.match(raw)):
        return int(match.group(1)) * _UNITS[match.group(2)]
    raise ValueError("Invalid ttl")


def _expire_at(ttl: timedelta) -> str:
    expires_at = datetime.now(UTC) + ttl
    return expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
