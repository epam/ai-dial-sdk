from typing import Optional


class DIALException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        type: str = "runtime_error",
        param: Optional[str] = None,
        code: Optional[str] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.type = type
        self.param = param
        self.code = code

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return f"{class_name}(status_code={self.status_code!r}, message={self.message!r})"
