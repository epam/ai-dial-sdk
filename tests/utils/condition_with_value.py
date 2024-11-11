import asyncio
from typing import Generic, TypeVar

_T = TypeVar("_T")


class ConditionWithValue(asyncio.Condition, Generic[_T]):
    _SENTINEL: object = object()
    _value: _T

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = self._SENTINEL  # type: ignore

    async def wait_for_value(self) -> _T:
        await self.wait_for(lambda: self._value is not self._SENTINEL)
        return self._value

    def set_value(self, value: _T):
        self._value = value
        self.notify_all()
