from pathlib import Path
from dataclasses import dataclass
from models.adapters.yolo_adapter import device
from config.settings import ROOT

@dataclass
class PoseObservation:
    person_id: int
    box: tuple
    pose: object

class PoseExtractor:
    """Pretrained pose + ByteTrack. This is NOT a drowning classifier."""
    def __init__(self, path='yolov8n-pose.pt'):
        from ultralytics import YOLO
        p = Path(path)
        if not p.is_absolute():
            p = ROOT/'models'/p.name if p.name == str(p) else ROOT/p
        # Ultralytics downloads known model names on first use if absent.
        self.model = YOLO(str(p))
        if self.model.task != 'pose':
            raise ValueError('Pose extractor cần model YOLO pose với 17 COCO keypoints.')
        self.device = device()

    def extract(self, frame):
        # Pool cameras are usually wide-angle and swimmers occupy few pixels.
        # A larger inference size and a slightly lower confidence threshold
        # improve recall without fabricating detections when nobody is found.
        r = self.model.track(
            frame,
            persist=True,
            tracker='bytetrack.yaml',
            device=self.device,
            imgsz=960,
            conf=0.15,
            iou=0.50,
            verbose=False,
        )[0]
        if r.boxes is None or r.boxes.id is None or r.keypoints is None:
            return []
        points = r.keypoints.xyn.cpu().numpy()
        if points.shape[1:] != (17,2):
            raise ValueError('Pose model phải trả về 17 keypoints COCO (x,y).')
        return [PoseObservation(int(identity),tuple(box),pose)
                for identity,box,pose in zip(r.boxes.id.cpu().tolist(),r.boxes.xyxy.cpu().tolist(),points)]
