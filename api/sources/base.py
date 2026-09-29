from abc import ABC, abstractmethod

class VideoSource(ABC):
    name = "Unknown"

    @abstractmethod
    async def search(self, query: str, limit: int = 25):
        raise NotImplementedError
