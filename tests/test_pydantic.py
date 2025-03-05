import pytest
from pydantic import BaseModel as NativeBaseModel

from aidial_sdk.pydantic._compat import USE_PYDANTIC_V2
from aidial_sdk.pydantic._compat import BaseModel as DialBaseModel
from aidial_sdk.pydantic._version import INSTALLED_PYDANTIC_V2
from tests.utils._pydantic import model_dump

pytestmark = pytest.mark.skipif(
    not USE_PYDANTIC_V2 and INSTALLED_PYDANTIC_V2,
    reason="Pydantic v1 and v2 models aren't compatible",
)


class DialSubStruct(DialBaseModel):
    x: int
    y: str


class NativeSubStruct(NativeBaseModel):
    x: int
    y: str


def test_native_pydantic():
    assert model_dump(NativeSubStruct(x=1, y="2")) == {"x": 1, "y": "2"}


def test_dial_pydantic():
    assert DialSubStruct(x=1, y="2").model_dump() == {"x": 1, "y": "2"}


def test_pydantic_dial_in_native_compatibility():
    class NativeStruct(NativeBaseModel):
        z: DialSubStruct

    assert model_dump(NativeStruct(z=DialSubStruct(x=1, y="2"))) == {
        "z": {"x": 1, "y": "2"}
    }


def test_pydantic_native_in_dial_compatibility():
    class DialStruct(DialBaseModel):
        z: NativeSubStruct

    assert DialStruct(z=NativeSubStruct(x=1, y="2")).model_dump() == {
        "z": {"x": 1, "y": "2"}
    }
