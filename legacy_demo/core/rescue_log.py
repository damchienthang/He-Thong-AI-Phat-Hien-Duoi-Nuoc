from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json


class RescueLog:
    """Local audit log for lifeguard acknowledgements.

    This boundary can later be replaced by a WebSocket/API client without
    changing the dashboard widgets.
    """

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def confirm(self, person_id, state, confidence, video_seconds, source):
        now = datetime.now(timezone.utc)
        record = {
            "event_id": uuid4().hex,
            "action": "rescue_confirmed",
            "person_id": int(person_id),
            "scope": "frame" if int(person_id) == 0 else "person",
            "state": state,
            "confidence": float(confidence),
            "video_seconds": float(video_seconds),
            "source": source,
            "confirmed_at": now.isoformat(),
        }
        path = self.root / f"rescue_{now.strftime('%Y%m%d_%H%M%S')}_{record['event_id'][:8]}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

