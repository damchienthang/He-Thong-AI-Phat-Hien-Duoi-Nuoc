from pathlib import Path
import numpy as np
import torch
from config.settings import CLASSES
from models.temporal_lstm import TemporalLSTM
from models.adapters.base import BasePredictor, Prediction
from models.adapters.yolo_adapter import device
from core.tracker import PersonBuffers

class MockTemporalPredictor:
    is_demo = True
    name = 'Scripted temporal demo'
    def predict_sequence(self, sequence, timestamp):
        if sequence.ndim != 3 or sequence.shape[1:] != (17,2):
            raise ValueError('Sequence cần shape (T,17,2).')
        # Deterministic scenario for alarm demonstrations, not a learned decision.
        phase = timestamp % 20
        return ('swimming' if phase < 4 else 'drowning' if phase < 15 else 'out_of_water',0.92)

class LSTMPredictor:
    def __init__(self, path, sequence_length=30):
        try:
            checkpoint = torch.load(path,map_location='cpu',weights_only=True)
            if not isinstance(checkpoint,dict):
                raise ValueError('Checkpoint phải là dictionary theo schema trong README.')
            expected = dict(format_version=1,architecture='TemporalLSTM',num_classes=3,
                            sequence_length=sequence_length,keypoints=17,coordinates=2,normalization='frame_xy_0_1')
            for key,value in expected.items():
                if checkpoint.get(key) != value:
                    raise ValueError(f'{key}: cần {value!r}, nhận {checkpoint.get(key)!r}.')
            classes = checkpoint.get('classes')
            if not isinstance(classes,list) or len(classes)!=3 or set(classes)!=set(CLASSES):
                raise ValueError('classes cần đủ 3 nhãn drowning/swimming/out_of_water theo đúng thứ tự lúc train.')
            hidden, layers = checkpoint.get('hidden_size'),checkpoint.get('num_layers')
            if type(hidden) is not int or not 1 <= hidden <= 1024 or type(layers) is not int or not 1 <= layers <= 8:
                raise ValueError('hidden_size/num_layers không hợp lệ.')
            if type(checkpoint.get('trained')) is not bool:
                raise ValueError('Checkpoint phải khai báo trained: true hoặc false.')
            self.device = device()
            self.model = TemporalLSTM(hidden,layers,3)
            self.model.load_state_dict(checkpoint['state_dict'],strict=True)
            self.model.to(self.device).eval()
            self.sequence_length, self.classes = sequence_length,classes
            self.is_demo = not checkpoint['trained']
            self.name = Path(path).name + (' [UNTRAINED]' if self.is_demo else '')
            self.predict_sequence(np.zeros((sequence_length,17,2),np.float32),0)
        except Exception as exc:
            raise ValueError(f'Checkpoint LSTM không tương thích: {exc}') from exc

    def predict_sequence(self, sequence, timestamp):
        sequence = np.asarray(sequence,dtype=np.float32)
        if sequence.shape != (self.sequence_length,17,2) or not np.isfinite(sequence).all():
            raise ValueError(f'Input cần ({self.sequence_length},17,2) hữu hạn.')
        if not ((sequence >= 0) & (sequence <= 1)).all():
            raise ValueError('Pose phải chuẩn hóa x/width, y/height trong [0,1].')
        with torch.inference_mode():
            logits = self.model(torch.from_numpy(sequence).unsqueeze(0).to(self.device))
            if tuple(logits.shape) != (1,3) or not torch.isfinite(logits).all():
                raise ValueError('Output model không hợp lệ.')
            probabilities = logits.softmax(-1)[0]
            index = int(probabilities.argmax().item())
            return self.classes[index],float(probabilities[index].item())

class TemporalPipeline(BasePredictor):
    def __init__(self, extractor, classifier, sequence_length=30):
        self.extractor,self.classifier = extractor,classifier
        self.buffers = PersonBuffers(sequence_length)
        self.is_demo,self.name = classifier.is_demo,classifier.name
        self.frame_index = 0

    def predict(self,frame,timestamp):
        observations = self.extractor.extract(frame)
        ready = self.buffers.update({o.person_id:o.pose for o in observations},self.frame_index)
        self.frame_index += 1
        results = []
        for o in observations:
            label,confidence = self.classifier.predict_sequence(ready[o.person_id],timestamp) if o.person_id in ready else ('warming_up',0.0)
            results.append(Prediction(o.person_id,label,confidence,o.box,o.pose,len(self.buffers.buffers.get(o.person_id,()))))
        return results
