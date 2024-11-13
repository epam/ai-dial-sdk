import sys

__all__ = ["TaskGroup"]

if sys.version_info >= (3, 11):
    from asyncio.taskgroups import TaskGroup
else:
    from aidial_sdk._third_party.asyncio_taskgroups import TaskGroup
