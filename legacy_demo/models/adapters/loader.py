from pathlib import Path

def load_model(path, mode, demo=False, sequence=30, pose_path='yolov8n-pose.pt'):
    try:
        if 'Mode A' in mode:
            if demo:
                from models.adapters.mock_adapter import MockPredictor
                return MockPredictor()
            if not Path(path).is_file():
                raise ValueError('Không tìm thấy model. Upload trọng số hoặc chọn đường dẫn có thật.')
            from models.adapters.yolo_adapter import YoloPredictor
            return YoloPredictor(path)
        from models.adapters.lstm_adapter import TemporalPipeline, LSTMPredictor, MockTemporalPredictor
        from core.pose_extractor import PoseExtractor
        classifier = MockTemporalPredictor() if demo else LSTMPredictor(path,sequence)
        return TemporalPipeline(PoseExtractor(pose_path),classifier,sequence)
    except Exception as exc:
        raise ValueError(f'Không load được model: {exc}') from exc
