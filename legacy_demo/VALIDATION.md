# Validation — 2026-09-23

## Environment actually used

Windows, Python 3.14.3, CPU. Streamlit 1.64.0, OpenCV 5.0.0 (wheel 5.0.0.93), PyTorch 2.14.0+cpu, Ultralytics 8.4.160, lap 0.5.13. Dependencies installed in project `.venv` with access to pre-existing system-site packages; no CUDA validation on this machine.

## Automated checks

`python -m pytest tests -q`: **12 passed**.

- Phase 1: alert progression/reset, video decode through EOF, snapshot/metadata, Streamlit AppTest missing video UI.
- Phase 2: YOLO classification and detection adapter contracts, mapping rejection (using controlled model outputs).
- Phase 3: distinct consecutive poses per ID, reset after gaps/disappearance, no repeated-frame padding, LSTM checkpoint generation/load/inference and incompatible sequence/state_dict rejection, warmup behavior.
- Phase 4: decoded incident clip frame count, pre/post-roll and truncated stop finalization, invalid metrics rejection, actual Streamlit Start/Stop controls using temporary video.

Generated video fixtures are temporary I/O test material, never presented as pool footage. No accuracy/precision/recall/F1 was computed or invented.

## Real-footage integration

`python -m tests.integration_smoke` completed successfully using downloaded licensed footage, actual OpenCV decode, actual YOLO pose + ByteTrack for Mode B, and scripted DEMO classifiers. Per-run details are in `tests/integration_result.json`.

| Pipeline | Frames | Classified observations | Incident transitions |
| --- | ---: | ---: | ---: |
| A, pool_demo.mp4 | 433 | 433 whole-frame predictions | 2 |
| B, pose_closeup.webm | 160 | 52 after genuine 30-pose warmup | 1 |

Integration uses warning=0.5 s, critical=1 s to exercise short clips. B observed track ID 6 in that run; IDs are tracker-assigned and not identities. Its short clip produced one warning transition, not a danger transition. Counts above are software execution checks, NOT research performance metrics. Incidents from integration were written to temporary directories and removed when testing ended.

The wide public-pool video did not yield stable detected people with the supplied lightweight pose estimator. A close-up outdoor-swimming clip was added to demonstrate actual sequence assembly; it is explicitly named in the UI and source/license documented. Missing detections are not replaced with fake boxes/poses. Mode A scripted predictions are independent of whether people are visible.

## Server / UI

Started `python -m streamlit run app.py --server.headless=true --server.address=127.0.0.1 --server.port=8501`. GET `http://127.0.0.1:8501/_stcore/health`: **200**, body **ok**.

Streamlit UI behavior tested through AppTest. Actual audible playback, browser autoplay permission, visual layout on every screen size, CUDA execution and future team-trained checkpoints have not been manually verified. Alarm WAV is generated locally; code triggers audio only on danger entry and retains the audio element long enough for playback. Test Alarm and Mute controls are available for browser verification.

## Model replacement limits

Demo LSTM was successfully loaded and inferred on CPU. Real YOLO drowning weights were not supplied; adapter behavior was tested with controlled outputs. Pretrained pose weights were downloaded and executed on actual footage. The checkpoint schema is documented in README: unrelated LSTM architectures require an adapter/architecture update rather than merely renaming a file.
