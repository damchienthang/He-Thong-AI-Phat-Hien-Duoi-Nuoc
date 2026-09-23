from pathlib import Path
import hashlib
import json
import time
import streamlit as st
from config.settings import ROOT, DEMO_NOTICE
from core.alert_manager import AlertManager
from core.dashboard_gateway import LocalDashboardGateway
from core.rescue_log import RescueLog
from core.video_processor import VideoProcessor
from models.adapters.mock_adapter import MockPredictor

st.set_page_config(page_title='CAM AI | Pool Safety', page_icon='🌊', layout='wide')
st.markdown("""<style>
.stApp {background: #081321; color: #e8f1fa;}
[data-testid="stSidebar"] {background: #101f30;}
[data-testid="stMetric"] {background: #12263a; border: 1px solid #24435d; border-radius: 12px; padding: 16px;}
h1 {letter-spacing: .12em;} .stButton button {border-radius: 9px;}
.status-card {border-radius: 12px; padding: 14px 16px; margin: 4px 0 14px 0; font-weight: 700; border: 1px solid rgba(255,255,255,.14);}
.status-normal {background: rgba(16,185,129,.18); color: #6ee7b7;}
.status-warning {background: rgba(245,158,11,.20); color: #fcd34d;}
.status-danger {background: rgba(239,68,68,.22); color: #fca5a5;}
.status-offline {background: rgba(100,116,139,.18); color: #cbd5e1;}
</style>""", unsafe_allow_html=True)
ss = st.session_state
ss.setdefault('running', False)
ss.setdefault('processor', None)
ss.setdefault('last_result', None)
ss.setdefault('message', '')
ss.setdefault('alarm_until', 0.0)
ss.setdefault('confirmed_rescues', set())
ss.setdefault('rescue_notice', '')
rescue_log = RescueLog(ROOT/'incidents'/'rescue_log')

def save_upload(upload):
    folder = ROOT / 'uploads'
    folder.mkdir(exist_ok=True)
    data = upload.getvalue()
    path = folder / (hashlib.sha256(data).hexdigest() + Path(upload.name).suffix.lower())
    if not path.exists():
        path.write_bytes(data)
    return path

with st.sidebar:
    st.title('🌊 CAM AI')
    st.caption('POOL SAFETY CONTROL CENTER')
    st.caption('Model status: loaded' if ss.processor else 'Model status: chưa load')
    st.subheader('MODEL')
    mode = st.selectbox('Pipeline', ['Mode A · Frame', 'Mode B · Temporal'], disabled=ss.running)
    demo = st.checkbox('Use Demo Model', True, disabled=ss.running)
    model_file = st.file_uploader('Upload model (.pt/.pth)', type=['pt','pth'], disabled=ss.running)
    model_path = st.text_input('Model path', 'models/best.pt', disabled=ss.running)
    pose_path = st.text_input('Pretrained pose model', 'yolov8n-pose.pt', disabled=ss.running) if 'Mode B' in mode else ''
    if 'Mode B' in mode:
        st.caption('YOLO pose pretrained chỉ lấy pose; classifier temporal là model riêng.')
    st.caption('Thiết lập được áp dụng khi Start / Restart. Chỉ load model từ nguồn tin cậy.')
    st.subheader('VIDEO SOURCE')
    source = st.radio('Source', ['Upload Video', 'Use Demo Pool Video'], disabled=ss.running)
    upload = st.file_uploader('Video', type=['mp4','avi','mov','mkv','webm'], disabled=ss.running) if source == 'Upload Video' else None
    demo_sample = st.selectbox('Demo footage', ['Pool overview', 'Pose close-up (bơi ngoài trời)'], disabled=ss.running) if source == 'Use Demo Pool Video' else 'Pool overview'
    demo_video = ROOT/'assets/demo'/('pool_demo.mp4' if demo_sample == 'Pool overview' else 'pose_closeup.webm')
    if source == 'Use Demo Pool Video' and demo_sample != 'Pool overview':
        st.caption('Clip cận cảnh dài 5 giây để xem pose/sequence; dùng ngưỡng 0.5s/1s nếu muốn thử alert demo.')
    st.subheader('ALERT SETTINGS')
    confidence = st.slider('Confidence threshold', 0.0, 1.0, 0.70, disabled=ss.running)
    warning = st.slider('Warning duration (s)', 0.5, 10.0, 2.0, 0.5, disabled=ss.running)
    critical = st.slider('Critical duration (s)', warning+0.5, 20.0, max(4.0,warning+0.5), 0.5, disabled=ss.running)
    sequence = st.number_input('Sequence length', 2, 120, 30, disabled=ss.running or 'Mode A' in mode)
    alarm_enabled = st.toggle('🔔 Bật cảnh báo âm thanh', True)
    if st.button('🔊 Test Alarm', disabled=not alarm_enabled):
        st.audio(str(ROOT/'assets/sounds/alert.wav'), autoplay=True)
    st.caption('Tắt nút trên chỉ tắt chuông; phát hiện, incident và log vẫn hoạt động.')

st.title('CAM AI')
st.caption('AI Drowning Detection & Pool Safety Monitoring')
processor = ss.processor
st.write('🟢 SYSTEM ONLINE' if ss.running else '⚪ SYSTEM READY')
st.caption(f'Model: {processor.predictor.name if processor else "Chưa load"}  •  Mode: {mode}  •  Source: {source}')
if (processor and processor.predictor.is_demo) or (not processor and demo):
    st.warning(DEMO_NOTICE)
st.caption('Demo đồ án: chưa được xác thực để thay thế người giám sát hồ bơi.')

start_col, stop_col, _ = st.columns([1,1,5])
if start_col.button('▶ Start / Restart', disabled=ss.running, type='primary'):
    try:
        if processor:
            processor.close()
        ss.processor, ss.last_result = None, None
        path = save_upload(upload) if upload else demo_video if source == 'Use Demo Pool Video' else None
        if path is None or not path.is_file():
            raise ValueError('Demo video chưa được cài đặt. Hãy upload video hoặc thêm pool_demo.mp4.' if source == 'Use Demo Pool Video' else 'Hãy upload video trước khi Start.')
        if demo and 'Mode A' in mode:
            predictor = MockPredictor()
        else:
            from models.adapters.loader import load_model
            chosen = save_upload(model_file) if model_file else ROOT/model_path
            with st.spinner('Đang load model...'):
                predictor = load_model(chosen, mode, demo, int(sequence), pose_path)
            if model_file and not demo:
                predictor.name = model_file.name + (' [UNTRAINED]' if predictor.is_demo else '')
        ss.processor = VideoProcessor(path, predictor, AlertManager(confidence,warning,critical), ROOT/'incidents')
        if upload:
            ss.processor.source = upload.name
        ss.running, ss.last_result, ss.message = True, None, ''
        ss.alarm_until = 0.0
        ss.confirmed_rescues = set()
        ss.rescue_notice = ''
        st.rerun()
    except Exception as exc:
        ss.message = f'Không thể khởi động: {exc}'
if stop_col.button('■ Stop', disabled=not ss.running):
    ss.processor.close()
    ss.running = False
    st.rerun()
if ss.message:
    st.info(ss.message)

monitor_tab, incidents_tab, evaluation_tab = st.tabs(['LIVE MONITOR', 'RECENT INCIDENTS', 'MODEL EVALUATION'])
with monitor_tab:
    @st.fragment(run_every=0.05 if ss.running else None)
    def monitor():
        event = False
        if ss.running:
            try:
                result = ss.processor.step()
                if result is None:
                    ss.running, ss.message = False, 'Đã xử lý xong video.'
                    st.rerun()
                ss.last_result = result
                event = any(a.entered_danger for a in result[2].values())
            except Exception as exc:
                ss.processor.close()
                ss.running, ss.message = False, f'Đã dừng xử lý: {exc}'
                st.rerun()
        left, right = st.columns([3,1])
        result = ss.last_result
        with left:
            st.subheader('VIDEO MONITOR')
            if result:
                frame, predictions, states, timestamp, _ = result
                st.image(frame, channels='BGR', width='stretch')
                st.caption(f'Video time {timestamp:.2f}s · frame {ss.processor.index} · xử lý mọi frame, tốc độ tùy máy')
            else:
                st.info('Chọn video và nhấn Start để bắt đầu giám sát.')
                if source == 'Use Demo Pool Video' and not demo_video.exists():
                    st.info('Demo video chưa được cài đặt. Hãy upload video hoặc thêm pool_demo.mp4.')
        with right:
            st.subheader('SYSTEM STATUS')
            predictions, states = (result[1],result[2]) if result else ([],{})
            events = LocalDashboardGateway.events(predictions, states)
            overall = ('DANGER' if any(e.state == 'DANGER' for e in events)
                       else 'SUSPICIOUS' if any(e.state == 'SUSPICIOUS' for e in events)
                       else 'NORMAL' if events else 'NO DATA')
            css = {'DANGER':'status-danger','SUSPICIOUS':'status-warning',
                   'NORMAL':'status-normal','NO DATA':'status-offline'}[overall]
            label = {'DANGER':'🔴 NGUY HIỂM','SUSPICIOUS':'🟡 CẢNH BÁO',
                     'NORMAL':'🟢 BÌNH THƯỜNG','NO DATA':'⚪ CHƯA CÓ DỮ LIỆU'}[overall]
            st.markdown(f'<div class="status-card {css}">{label}</div>', unsafe_allow_html=True)
            st.caption('🔄 Local realtime stream · sẵn sàng nối FastAPI/WebSocket')
            tracked = len({p.person_id for p in predictions if p.person_id != 0})
            st.metric('Tracked persons', tracked)
            for label, state in [('Normal','NORMAL'),('Suspicious','SUSPICIOUS'),('Danger','DANGER')]:
                st.metric(label, sum(states[p.person_id].state == state and p.label != 'warming_up' for p in predictions))
            if any(p.person_id == 0 for p in predictions):
                st.caption('Frame classification: trạng thái toàn cảnh, không đếm người.')
            warming = sum(p.label == 'warming_up' for p in predictions)
            if warming:
                st.caption(f'{warming} người đang tích lũy pose; chưa có kết luận phân loại.')
            active = [p for p in predictions if states[p.person_id].state != 'NORMAL']
            if not predictions:
                st.info('Model không nhận được người trong frame này. Hãy dùng video rõ hơn, người lớn hơn trong khung hình, hoặc Mode A với model detection phù hợp. Trạng thái này không có nghĩa hồ bơi an toàn.')
            elif not active:
                st.success('✓ NO ACTIVE ALERT')
            for p in active:
                a = states[p.person_id]
                st.error(f'⚠ DROWNING RISK DETECTED · {a.state}')
                st.write(f'{"FRAME" if p.person_id == 0 else "Person ID: " + str(p.person_id)} · {p.confidence:.0%} · {a.duration:.1f} s')
                rescue_key = (ss.processor.source, int(p.person_id), a.state)
                if rescue_key in ss.confirmed_rescues:
                    st.success('✅ Cứu hộ đã xác nhận')
                elif st.button(
                    '🛟 Xác nhận đã triển khai cứu hộ',
                    key=f'rescue-{ss.processor.source}-{p.person_id}-{a.state}',
                    type='primary',
                ):
                    record = rescue_log.confirm(
                        p.person_id, a.state, p.confidence, timestamp,
                        ss.processor.source,
                    )
                    ss.confirmed_rescues.add(rescue_key)
                    ss.rescue_notice = f'Đã ghi nhận cứu hộ lúc {record["confirmed_at"]}.'
                    st.rerun(scope='fragment')
            if ss.rescue_notice:
                st.caption(ss.rescue_notice)
            if event:
                ss.alarm_until = time.monotonic() + 2.0
            if time.monotonic() < ss.alarm_until and alarm_enabled:
                st.audio(str(ROOT/'assets/sounds/alert.wav'), autoplay=True)
    monitor()
with incidents_tab:
    st.subheader('RECENT INCIDENTS')
    st.button('Refresh incidents')
    st.caption('Snapshot + metadata tại WARNING và DANGER; clip có 2 giây trước/sau. Refresh để cập nhật.')
    paths = sorted((ROOT/'incidents').glob('*/metadata.json'), reverse=True)[:20]
    if not paths:
        st.info('Chưa có incident.')
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            with st.expander(f'{data["timestamp"]} · {data["state"]} · {data["confidence"]:.0%}'):
                st.json(data)
                st.image(str(path.parent/'snapshot.jpg'), width=400)
                st.download_button('Download metadata', path.read_bytes(), file_name=path.parent.name+'.json', key=str(path))
                st.download_button('Download snapshot', (path.parent/'snapshot.jpg').read_bytes(), file_name=path.parent.name+'.jpg', key=str(path)+'jpg')
                clip = path.parent/'clip.mp4'
                if clip.exists() and data.get('clip_status') in ('complete','partial'):
                    st.download_button('Download clip', clip.read_bytes(), file_name=path.parent.name+'.mp4', key=str(path)+'clip')
        except (OSError,ValueError,KeyError) as exc:
            st.warning(f'Không đọc được incident {path.parent.name}: {exc}')
with evaluation_tab:
    from core.evaluation import validate_metrics
    st.subheader('MODEL EVALUATION')
    metrics_file = st.file_uploader('Upload metrics.json từ đánh giá thực nghiệm', type=['json'])
    st.caption('Chỉ hiển thị số liệu do nhóm cung cấp; app không tự tạo hoặc xác minh metrics.')
    active_demo = ss.processor.predictor.is_demo if ss.processor else demo
    if active_demo:
        st.info('No evaluation results available')
        st.caption('Demo/UNTRAINED không có Accuracy, Precision, Recall hay F1.')
    else:
        try:
            local = ROOT/'metrics.json'
            data = json.loads(metrics_file.getvalue()) if metrics_file else json.loads(local.read_text(encoding='utf-8')) if local.exists() else None
            if data is None:
                st.info('No evaluation results available')
            else:
                values = validate_metrics(data)
                for column,(key,value) in zip(st.columns(4),values.items()):
                    column.metric(key.title(),f'{value:.1%}')
                st.caption('Nguồn: metrics.json do người dùng cung cấp; đối chiếu đúng model và tập test trước khi báo cáo.')
        except (ValueError,OSError) as exc:
            st.error(f'Metrics không hợp lệ: {exc}')
