from abc import ABC, abstractmethod

from aidial_sdk.chat_completion.chunks import BaseChunk


class ChoiceBase(ABC):
    @property
    @abstractmethod
    def index(self) -> int:
        pass

    @property
    @abstractmethod
    def opened(self) -> bool:
        pass

    @property
    @abstractmethod
    def closed(self) -> bool:
        pass

    @property
    @abstractmethod
    def has_function_call(self) -> bool:
        pass

    @abstractmethod
    def send_chunk(self, chunk: BaseChunk) -> None:
        pass
