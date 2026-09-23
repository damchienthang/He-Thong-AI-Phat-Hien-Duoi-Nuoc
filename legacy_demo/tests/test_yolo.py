from types import SimpleNamespace
import pytest
import torch
from models.adapters.yolo_adapter import YoloPredictor

class FakeModel:
    task = 'classify'
    names = {0:'drowning',1:'swimming',2:'out_of_water'}
    def predict(self,*args,**kwargs):
        return [SimpleNamespace(probs=SimpleNamespace(top1=1,top1conf=torch.tensor(.87)))]

def test_classification_frame_scope():
    p = YoloPredictor('test.pt',model=FakeModel()).predict(None,0)[0]
    assert p.person_id == 0 and p.box is None and p.label == 'swimming'
    assert p.confidence == pytest.approx(.87)

def test_invalid_mapping():
    with pytest.raises(ValueError,match='Class model'):
        YoloPredictor('test.pt',mapping={'drowning':'wrong'},model=FakeModel())

def test_detection_tracks():
    model = FakeModel()
    model.task = 'detect'
    def track(*args,**kwargs):
        assert kwargs['persist'] and kwargs['tracker'] == 'bytetrack.yaml'
        return [SimpleNamespace(boxes=SimpleNamespace(id=torch.tensor([3]),cls=torch.tensor([0]),conf=torch.tensor([.9]),xyxy=torch.tensor([[1,2,3,4]])))]
    model.track = track
    p = YoloPredictor('test.pt',model=model).predict(None,0)[0]
    assert p.person_id == 3 and p.label == 'drowning' and p.box == (1,2,3,4)
