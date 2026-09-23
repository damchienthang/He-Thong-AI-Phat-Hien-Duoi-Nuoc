import json
import torch
from config.settings import ROOT, CLASSES
from models.adapters.base import BasePredictor, Prediction

def device():
    return 'cuda:0' if torch.cuda.is_available() else 'cpu'

class YoloPredictor(BasePredictor):
    def __init__(self, path, mapping=None, model=None):
        if model is None:
            from ultralytics import YOLO
            model = YOLO(str(path))
        self.model = model
        self.name = str(path).replace('\\','/').split('/')[-1]
        if self.model.task not in ('classify','detect'):
            raise ValueError('Mode A chỉ hỗ trợ YOLO classification hoặc detection.')
        self.mapping = mapping or json.loads((ROOT/'config/class_mapping.json').read_text(encoding='utf-8'))
        names = list(self.model.names.values()) if isinstance(self.model.names,dict) else self.model.names
        if any(self.mapping.get(name) not in CLASSES for name in names):
            raise ValueError('Class model không khớp. Cập nhật config/class_mapping.json; cần drowning/swimming/out_of_water.')
        self.device = device()

    def predict(self, frame, timestamp):
        if self.model.task == 'classify':
            result = self.model.predict(frame,device=self.device,verbose=False)[0]
            idx = int(result.probs.top1)
            return [Prediction(0,self.mapping[self.model.names[idx]],float(result.probs.top1conf))]
        result = self.model.track(frame,persist=True,tracker='bytetrack.yaml',device=self.device,verbose=False)[0]
        if result.boxes is None or result.boxes.id is None:
            return []
        return [Prediction(int(identity),self.mapping[self.model.names[int(cls)]],float(conf),tuple(box))
                for identity,cls,conf,box in zip(result.boxes.id.cpu().tolist(),result.boxes.cls.cpu().tolist(),result.boxes.conf.cpu().tolist(),result.boxes.xyxy.cpu().tolist())]
