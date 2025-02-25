from pydantic import BaseModel as NativeBaseModel

from aidial_sdk.pydantic_v1 import BaseModel as DialBaseModel


class DialSubStruct(DialBaseModel):
    x: int
    y: str


class NativeSubStruct(NativeBaseModel):
    x: int
    y: str


def test_native_pydantic():
    assert NativeSubStruct(x=1, y="2").dict() == {"x": 1, "y": "2"}


def test_dial_pydantic():
    assert DialSubStruct(x=1, y="2").dict() == {"x": 1, "y": "2"}


def test_pydantic_dial_in_native_compatibility():
    class NativeStruct(NativeBaseModel):
        z: DialSubStruct

    assert NativeStruct(z=DialSubStruct(x=1, y="2")).dict() == {
        "z": {"x": 1, "y": "2"}
    }


def test_pydantic_native_in_dial_compatibility():
    class DialStruct(DialBaseModel):
        z: NativeSubStruct

    assert DialStruct(z=NativeSubStruct(x=1, y="2")).dict() == {
        "z": {"x": 1, "y": "2"}
    }
