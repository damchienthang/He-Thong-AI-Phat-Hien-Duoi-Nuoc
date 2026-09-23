from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import cv2

class IncidentRecorder:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def record(self, frame, prediction, alert, timestamp, model, is_demo, source):
        now = datetime.now(timezone.utc)
        folder = self.root / (now.strftime('incident_%Y%m%d_%H%M%S_') + uuid4().hex[:8])
        folder.mkdir()
        ok, encoded = cv2.imencode('.jpg', frame)
        if not ok:
            raise OSError('Không thể tạo snapshot.')
        (folder / 'snapshot.jpg').write_bytes(encoded.tobytes())
        data = dict(person_id=prediction.person_id, scope='frame' if prediction.person_id == 0 else 'person',
                    **{'class': prediction.label}, confidence=prediction.confidence,
                    timestamp=now.isoformat(), duration=alert.duration, state=alert.state,
                    video_seconds=timestamp, model=model, is_demo=is_demo, source=source)
        (folder / 'metadata.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return folder
