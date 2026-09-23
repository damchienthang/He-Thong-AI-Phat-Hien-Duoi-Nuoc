from dataclasses import dataclass


@dataclass
class DashboardEvent:
    """Stable DTO expected from the future FastAPI/WebSocket backend."""

    person_id: int
    label: str
    confidence: float
    state: str
    duration: float


class LocalDashboardGateway:
    """Adapts the current in-process pipeline to the dashboard contract."""

    @staticmethod
    def events(predictions, states):
        return [
            DashboardEvent(
                person_id=p.person_id,
                label=p.label,
                confidence=p.confidence,
                state=states[p.person_id].state,
                duration=states[p.person_id].duration,
            )
            for p in predictions
        ]

