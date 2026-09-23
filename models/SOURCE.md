# Model sources

- `yolov8n-pose.pt`: Ultralytics pretrained COCO pose estimator; downloaded by Ultralytics from https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n-pose.pt . This estimates pose only; it is NOT a trained drowning classifier.
- Upstream: https://github.com/ultralytics/ultralytics ; licensing: https://www.ultralytics.com/license and https://github.com/ultralytics/ultralytics/blob/main/LICENSE . Review upstream terms when redistributing/deploying.
- `demo_lstm.pth`: generated locally by `models.temporal_lstm.create_demo_checkpoint`, seed 42, random/untrained weights, `trained: false`; no training dataset or evaluation metrics.
- `best.pt` / `checkpoint.pth`: supplied by the research team later, not included and not claimed to exist.
