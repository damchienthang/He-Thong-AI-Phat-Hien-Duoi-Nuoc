import math
from pathlib import Path
import cv2
from core.incident_recorder import IncidentRecorder
from core.clip_recorder import ClipRecorder

class VideoProcessor:
    def __init__(self, path, predictor, alerts, incident_root, fallback_fps=25):
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            self.cap.release()
            raise ValueError('Không đọc được video. Hãy dùng MP4/H.264 hoặc AVI hợp lệ.')
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if math.isfinite(fps) and 1 <= fps <= 240 else fallback_fps
        self.total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.predictor, self.alerts = predictor, alerts
        self.recorder = IncidentRecorder(incident_root)
        self.index, self.closed = 0, False
        self.clips = ClipRecorder(self.fps)
        self.source = Path(path).name

    def step(self):
        ok, frame = self.cap.read()
        if not ok:
            self.close()
            return None
        timestamp = self.index / self.fps
        self.index += 1
        # Bound inference/display and recording memory without changing aspect ratio.
        h, w = frame.shape[:2]
        scale = min(960 / w, 640 / h, 1.0)
        if scale < 1:
            frame = cv2.resize(frame, (max(1,int(w * scale)), max(1,int(h * scale))))
        predictions = self.predictor.predict(frame, timestamp)
        states = self.alerts.update(predictions, timestamp)
        canvas = frame.copy()
        for i, p in enumerate(predictions):
            a = states[p.person_id]
            color = (60, 60, 240) if a.state == 'DANGER' else (0, 190, 255) if a.state == 'SUSPICIOUS' else (150, 220, 30)
            x, y = 15, 55 + i * 27
            if p.box is not None:
                x1,y1,x2,y2 = map(int, p.box)
                cv2.rectangle(canvas, (x1,y1), (x2,y2), color, 2)
                x,y = max(0,x1), max(50,y1-8)
            if p.pose is not None:
                for px,py in p.pose:
                    if px > 0 and py > 0:
                        cv2.circle(canvas,(int(px*canvas.shape[1]),int(py*canvas.shape[0])),3,color,-1)
            identity = 'FRAME' if p.person_id == 0 else f'ID {p.person_id:02d}'
            text = f'{identity} {p.label.upper()} {p.confidence:.0%} | {a.state}'
            if p.label == 'warming_up':
                text += f' ({p.buffer_size} poses)'
            cv2.putText(canvas,text,(x,y),cv2.FONT_HERSHEY_SIMPLEX,0.5,color,2)
        if self.predictor.is_demo:
            # Keep the watermark compact so it never hides the monitored area
            # or gets clipped on portrait/low-resolution uploaded videos.
            badge = 'DEMO | NOT VALIDATED'
            (tw, th), baseline = cv2.getTextSize(
                badge, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1
            )
            cv2.rectangle(canvas, (8, 7), (18 + tw, 17 + th + baseline), (20, 35, 45), -1)
            cv2.putText(
                canvas, badge, (13, 12 + th), cv2.FONT_HERSHEY_SIMPLEX,
                0.48, (0, 210, 255), 1, cv2.LINE_AA
            )
        self.clips.push(canvas)
        incidents = []
        for p in predictions:
            a = states[p.person_id]
            if a.entered_warning or a.entered_danger:
                folder = self.recorder.record(canvas,p,a,timestamp,self.predictor.name,self.predictor.is_demo,self.source)
                incidents.append(folder)
                self.clips.start(folder,(canvas.shape[1],canvas.shape[0]))
        return canvas, predictions, states, timestamp, incidents

    def close(self):
        if not self.closed:
            self.cap.release()
            self.closed = True
            self.clips.close()

    def __del__(self):
        if hasattr(self, 'closed'):
            self.close()
