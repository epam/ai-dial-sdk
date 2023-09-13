try:
    from pydantic.v1 import *  # type: ignore
except ImportError:
    from pydantic import *  # type: ignore
