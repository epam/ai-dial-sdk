import json
from collections.abc import Callable, Coroutine
from typing import Any, Generic, ParamSpec, Protocol, TypeVar

from pydantic import BaseModel

from aidial_sdk.translators.messages_to_chat_completions.utils.log_config import (
    app_logger as log,
)

_P = ParamSpec("_P")
_T_co = TypeVar("_T_co", covariant=True)
_T = TypeVar("_T")

_Close = Callable[[_T], Coroutine[Any, Any, None]]


async def _close_value(close: _Close | None, func_name: str, value) -> None:
    if close is None:
        return

    try:
        await close(value)
    except Exception as e:
        log.error(f"Error on closing a cached value of {func_name}: {e}")


class _SyncCachedFunction(Protocol, Generic[_P, _T_co]):
    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> _T_co: ...
    async def clear(self) -> None: ...


def cache(
    close: _Close | None = None,
) -> Callable[[Callable[_P, _T]], _SyncCachedFunction[_P, _T]]:
    def wrapper(
        func: Callable[_P, _T],
    ) -> _SyncCachedFunction[_P, _T]:
        _cache: dict[str, _T] = {}

        func_name = f"{func.__module__}.{func.__qualname__}"

        class _Wrapper:
            def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> _T:
                key = _make_key(args, kwargs)

                if key not in _cache:
                    _cache[key] = func(*args, **kwargs)

                return _cache[key]

            async def clear(self) -> None:
                entries = list(_cache.values())
                _cache.clear()

                log.debug(f"Clearing cache {func_name}, {len(entries)} entries")

                for value in entries:
                    await _close_value(close, func_name, value)

        return _Wrapper()

    return wrapper


def _make_key(args: tuple, kwargs: dict) -> str:
    dump_args = {"sort_keys": True, "separators": (",", ":")}

    def default(obj):
        if isinstance(obj, BaseModel):
            return json.dumps(obj.model_dump(), **dump_args)
        raise TypeError(f"Cannot serialize object of type {type(obj)!r}")

    return json.dumps([args, kwargs], **dump_args, default=default)
