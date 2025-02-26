try:
    from pydantic.v1 import *  # type: ignore
    from pydantic.v1.main import ModelMetaclass  # type: ignore
except ImportError:
    from pydantic import *  # type: ignore
    from pydantic.main import ModelMetaclass  # type: ignore
