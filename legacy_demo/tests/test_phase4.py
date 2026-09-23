import json
import cv2
import numpy as np
import pytest
from core.clip_recorder import ClipRecorder
from core.evaluation import validate_metrics

def test_clips_pre_post_and_stop(tmp_path):
    recorder = ClipRecorder(10,pre_seconds=1,post_seconds=1)
    frame = np.zeros((120,160,3),np.uint8)
    for i in range(20): recorder.push(frame)
    folder = tmp_path/'complete'; folder.mkdir()
    (folder/'metadata.json').write_text('{}')
    recorder.start(folder,(160,120))
    for i in range(10): recorder.push(frame)
    data = json.loads((folder/'metadata.json').read_text())
    assert data['clip_status'] == 'complete' and data['clip_frames'] == 20
    cap = cv2.VideoCapture(str(folder/'clip.mp4'))
    assert cap.isOpened() and int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 20
    cap.release()
    folder2 = tmp_path/'partial'; folder2.mkdir()
    (folder2/'metadata.json').write_text('{}')
    recorder.start(folder2,(160,120))
    recorder.close()
    assert json.loads((folder2/'metadata.json').read_text())['clip_status'] == 'partial'

def test_metrics_reject_invalid():
    assert validate_metrics(dict(accuracy=.8,precision=.7,recall=.6,f1=.65))['accuracy'] == .8
    for bad in [float('nan'),True,1.1,-.1,'90%']:
        with pytest.raises(ValueError):
            validate_metrics(dict(accuracy=bad,precision=.7,recall=.6,f1=.65))
