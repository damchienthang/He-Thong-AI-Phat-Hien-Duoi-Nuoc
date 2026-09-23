"""Manual real-footage check; no accuracy metrics and no pool footage fabricated."""
import json
import tempfile
from pathlib import Path
from core.alert_manager import AlertManager
from core.video_processor import VideoProcessor
from models.adapters.loader import load_model
from config.settings import ROOT

def main():
    reports = []
    with tempfile.TemporaryDirectory() as temporary:
        for mode,filename in [('Mode A','pool_demo.mp4'),('Mode B','pose_closeup.webm')]:
            predictor = load_model(None,mode,True)
            processor = VideoProcessor(ROOT/'assets/demo'/filename,predictor,AlertManager(warning=.5,critical=1),Path(temporary)/mode)
            ids, ready, events = set(),0,0
            while True:
                result = processor.step()
                if result is None:break
                ids.update(p.person_id for p in result[1] if p.person_id)
                ready += sum(p.label != 'warming_up' for p in result[1])
                events += len(result[4])
            processor.close()
            assert ready > 0
            if mode == 'Mode B': assert ids
            reports.append(dict(mode=mode,video=filename,frames=processor.index,tracked_ids=sorted(ids),classified_observations=ready,incident_events=events))
    print(json.dumps(reports,indent=2))
    (ROOT/'tests/integration_result.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')

if __name__ == '__main__':main()
