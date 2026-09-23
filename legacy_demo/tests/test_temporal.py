import numpy as np
import pytest
import torch
from core.tracker import PersonBuffers
from core.pose_extractor import PoseObservation
from models.temporal_lstm import create_demo_checkpoint
from models.adapters.lstm_adapter import LSTMPredictor, TemporalPipeline, MockTemporalPredictor

def test_person_buffers_real_sequence_and_gap():
    buffers = PersonBuffers(30)
    for i in range(30):
        result = buffers.update({1:np.full((17,2),i/100),2:np.full((17,2),.9-i/100)},i)
        if i < 29:
            assert not result
    assert result[1].shape == (30,17,2)
    assert result[1][0,0,0] == 0 and result[1][-1,0,0] == pytest.approx(.29)
    assert result[2][0,0,0] == pytest.approx(.9)
    buffers.update({2:np.ones((17,2))},30)
    assert 1 not in buffers.buffers
    assert 1 not in buffers.update({1:np.ones((17,2))},31)
    assert len(buffers.buffers[1]) == 1
    assert not buffers.update({1:np.ones((17,2))},33)
    assert len(buffers.buffers[1]) == 1

def test_checkpoint(tmp_path):
    path = tmp_path/'demo.pth'
    create_demo_checkpoint(path)
    predictor = LSTMPredictor(path)
    assert predictor.is_demo
    label, conf = predictor.predict_sequence(np.zeros((30,17,2),np.float32),0)
    assert label in predictor.classes and 0 <= conf <= 1
    with pytest.raises(ValueError,match='sequence_length'):
        LSTMPredictor(path,20)
    checkpoint = torch.load(path,weights_only=True)
    checkpoint['state_dict']['fc.weight'] = torch.zeros((4,64))
    torch.save(checkpoint,path)
    with pytest.raises(ValueError,match='không tương thích'):
        LSTMPredictor(path)

def test_temporal_warmup():
    class Extractor:
        i = 0
        def extract(self,frame):
            self.i += 1
            return [PoseObservation(8,(1,2,30,40),np.full((17,2),self.i/100))]
    pipeline = TemporalPipeline(Extractor(),MockTemporalPredictor(),30)
    for i in range(29):
        assert pipeline.predict(None,i/10)[0].label == 'warming_up'
    assert pipeline.predict(None,5)[0].label == 'drowning'
    assert pipeline.buffers.buffers[8][0][0,0] != pipeline.buffers.buffers[8][-1][0,0]
