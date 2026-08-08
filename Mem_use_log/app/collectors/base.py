from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseCollector(ABC):
    @abstractmethod
    def collect(self) -> Dict[str, Any]:
        """
        Collects data and returns it as a dictionary.
        Returns empty dict or handles errors gracefully if collection fails.
        """
        pass
