try:
    from pydantic.v1 import *  # type: ignore
except ImportError:
    from pydantic import *  # type: ignore

from pydantic.v1.error_wrappers import ErrorWrapper  # type: ignore
from pydantic.v1.validators import make_literal_validator  # type: ignore
