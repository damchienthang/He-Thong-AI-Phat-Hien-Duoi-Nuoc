from dataclasses import dataclass

@dataclass
class Alert:
    state: str = 'NORMAL'
    duration: float = 0.0
    entered_warning: bool = False
    entered_danger: bool = False

class AlertManager:
    def __init__(self, confidence=0.7, warning=2.0, critical=4.0):
        if not 0 <= confidence <= 1 or not 0 < warning < critical:
            raise ValueError('Cần 0 < warning < critical và confidence trong [0,1].')
        self.confidence, self.warning, self.critical = confidence, warning, critical
        self.active = {}

    def update(self, predictions, timestamp):
        ids = {p.person_id for p in predictions}
        self.active = {k:v for k,v in self.active.items() if k in ids}
        result = {}
        for p in predictions:
            previous = self.active.get(p.person_id)
            risky = p.label == 'drowning' and p.confidence >= self.confidence
            if not risky:
                self.active.pop(p.person_id, None)
                result[p.person_id] = Alert()
                continue
            start, old = previous if previous else (timestamp, 'NORMAL')
            duration = max(0, timestamp - start)
            state = 'DANGER' if duration >= self.critical else 'SUSPICIOUS' if duration >= self.warning else 'NORMAL'
            self.active[p.person_id] = (start, state)
            result[p.person_id] = Alert(state, duration, state == 'SUSPICIOUS' and old == 'NORMAL', state == 'DANGER' and old != 'DANGER')
        return result
