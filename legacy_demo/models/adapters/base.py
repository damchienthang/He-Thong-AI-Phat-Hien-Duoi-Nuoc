from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Prediction:
    person_id: int
    label: str
    confidence: float
    box: tuple | None = None
    pose: object = None
    buffer_size: int = 0

class BasePredictor(ABC):
    is_demo = False
    name = 'Model'
    @abstractmethod
    def predict(self, frame, timestamp):
        raise NotImplementedError
