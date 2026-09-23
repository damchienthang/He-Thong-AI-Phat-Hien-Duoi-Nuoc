import tempfile
from pathlib import Path
import cv2
import numpy as np
from core.alert_manager import AlertManager
from core.video_processor import VideoProcessor
from models.adapters.mock_adapter import MockPredictor
from models.adapters.base import Prediction

def test_alert_transitions_and_missing_person():
    manager = AlertManager(warning=1, critical=2)
    p = Prediction(1, 'drowning', .9)
    assert manager.update([p],0)[1].state == 'NORMAL'
    assert manager.update([p],1)[1].entered_warning
    assert manager.update([p],2)[1].entered_danger
    assert not manager.update([p],3)[1].entered_danger
    manager.update([],4)
    assert manager.update([p],5)[1].duration == 0
    assert manager.update([Prediction(1,'swimming',.9)],6)[1].state == 'NORMAL'

def test_video_demo_incident(tmp_path):
    # Generated test fixture only: never offered as pool footage.
    path = tmp_path/'fixture.avi'
    writer = cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(160,120))
    assert writer.isOpened()
    for i in range(110):
        writer.write(np.full((120,160,3),i,dtype=np.uint8))
    writer.release()
    proc = VideoProcessor(path,MockPredictor(),AlertManager(),tmp_path/'incidents')
    count = 0
    while proc.step() is not None:
        count += 1
    assert count == 110 and proc.closed
    records = list((tmp_path/'incidents').glob('*/metadata.json'))
    assert len(records) == 2
    assert all(p.with_name('snapshot.jpg').is_file() for p in records)

def test_ui_initial(tmp_path, monkeypatch):
    import config.settings
    monkeypatch.setattr(config.settings, "ROOT", tmp_path)
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(Path('app.py').resolve()).run(timeout=30)
    assert not app.exception
    app.radio[0].set_value('Use Demo Pool Video').run()
    assert not app.exception
    next(b for b in app.button if 'Start / Restart' in b.label).click().run()
    assert not app.exception




def test_ui_demo_start_stop(tmp_path,monkeypatch):
    import config.settings
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(config.settings,'ROOT',tmp_path)
    demo = tmp_path/'assets/demo'
    demo.mkdir(parents=True)
    writer = cv2.VideoWriter(str(demo/'pool_demo.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),10,(160,120))
    assert writer.isOpened()
    for _ in range(50):writer.write(np.zeros((120,160,3),np.uint8))
    writer.release()
    app = AppTest.from_file(Path('app.py').resolve()).run(timeout=30)
    app.radio[0].set_value('Use Demo Pool Video').run()
    next(b for b in app.button if 'Start / Restart' in b.label).click().run()
    assert not app.exception and app.session_state['running']
    assert app.session_state['processor'].index > 0
    next(b for b in app.button if 'Stop' in b.label).click().run()
    assert not app.exception and not app.session_state['running']
    assert app.session_state['processor'].closed
