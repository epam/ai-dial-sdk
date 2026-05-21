class CacheBreakpointPath:
    path: str

    def __init__(self, path: str) -> None:
        self.path = path

    @classmethod
    def messages(cls, idx: int):
        return cls(f"prefix.body.messages[{idx}]")

    @classmethod
    def tools(cls, idx: int):
        return cls(f"prefix.body.tools[{idx}]")
