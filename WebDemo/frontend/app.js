/**
 * AI Drowning Detection – Dashboard App Logic
 * Nhóm 7 – PPLNCKH 2026
 * 
 * Kết nối WebSocket với backend FastAPI, xử lý detection results,
 * cập nhật UI theo thời gian thực.
 */

'use strict';

// ─── Configuration ──────────────────────────────────────────────────────────
const CONFIG = {
  WS_BASE: `ws://${location.hostname}:8000/ws`,
  API_BASE: `http://${location.hostname}:8000/api`,
  DEMO_WS: null, // assigned below
  VIDEO_WS: null,
  DANGER_THRESHOLD: 0.5,
  WARN_THRESHOLD:   0.3,
  ALERT_SOUND: true,
  FPS_WINDOW: 30,
};

CONFIG.DEMO_WS  = `${CONFIG.WS_BASE}/demo`;
CONFIG.VIDEO_WS = `${CONFIG.WS_BASE}/video`;

// ─── State ───────────────────────────────────────────────────────────────────
const state = {
  ws: null,
  mode: 'idle',           // 'idle' | 'demo' | 'camera' | 'upload'
  frameCount: 0,
  lastFrameTime: 0,
  fpsBuffer: [],
  safeCount: 0,
  warnCount: 0,
  dangerCount: 0,
  totalAlerts: 0,
  zoneData: {},
  alerts: [],
  cameraStream: null,
  videoInterval: null,
  lastAlertModalTime: 0,  // anti-spam for modal
};

// ─── DOM References ─────────────────────────────────────────────────────────
const dom = {
  canvas:          document.getElementById('videoCanvas'),
  videoOverlay:    document.getElementById('videoOverlay'),
  btnUpload:       document.getElementById('btnUpload'),
  btnUploadVideo:  document.getElementById('btnUploadVideo'),
  btnCamera:       document.getElementById('btnCamera'),
  fileInput:       document.getElementById('fileInput'),
  videoFileInput:  document.getElementById('videoFileInput'),
  uploadedVideo:   document.getElementById('uploadedVideo'),
  videoPlayerBar:  document.getElementById('videoPlayerBar'),
  vbarPlayPause:   document.getElementById('vbarPlayPause'),
  vbarTime:        document.getElementById('vbarTime'),
  vbarProgress:    document.getElementById('vbarProgress'),
  vbarStop:        document.getElementById('vbarStop'),
  statusDot:       document.getElementById('statusDot'),
  statusText:      document.getElementById('statusText'),
  modeLabel:       document.getElementById('modeLabel'),
  headerTime:      document.getElementById('headerTime'),
  fpsDisplay:      document.getElementById('fpsDisplay'),
  frameCount:      document.getElementById('frameCount'),
  personCount:     document.getElementById('personCount'),
  safeCount:       document.getElementById('safeCount'),
  warnCount:       document.getElementById('warnCount'),
  dangerCount:     document.getElementById('dangerCount'),
  totalAlerts:     document.getElementById('totalAlerts'),
  zoneGrid:        document.getElementById('zoneGrid'),
  detectionList:   document.getElementById('detectionList'),
  detectionBadge:  document.getElementById('detectionBadge'),
  alertList:       document.getElementById('alertList'),
  alertModal:      document.getElementById('alertModal'),
  modalBody:       document.getElementById('modalBody'),
  modalClose:      document.getElementById('modalClose'),
  footerStats:     document.getElementById('footerStats'),
};

const ctx = dom.canvas.getContext('2d');

// ─── Initialization ─────────────────────────────────────────────────────────
function init() {
  buildZoneGrid();
  bindEvents();
  startClock();
  checkBackendStatus();
  drawIdleFrame();
}

function buildZoneGrid() {
  const cols = ['A', 'B', 'C', 'D'];
  const rows  = [1, 2, 3];
  dom.zoneGrid.innerHTML = '';
  
  rows.forEach(row => {
    cols.forEach(col => {
      const cellId = `${col}${row}`;
      const cell = document.createElement('div');
      cell.className = 'zone-cell safe';
      cell.id = `zone-${cellId}`;
      cell.innerHTML = `
        <span class="zone-label">${cellId}</span>
        <span class="zone-count" id="zone-count-${cellId}">0</span>
      `;
      dom.zoneGrid.appendChild(cell);
    });
  });
}

function bindEvents() {
  dom.btnUpload.addEventListener('click', () => dom.fileInput.click());
  dom.fileInput.addEventListener('change', handleFileUpload);
  if (dom.btnUploadVideo) dom.btnUploadVideo.addEventListener('click', () => dom.videoFileInput.click());
  if (dom.videoFileInput) dom.videoFileInput.addEventListener('change', handleVideoFileUpload);
  if (dom.vbarPlayPause) dom.vbarPlayPause.addEventListener('click', toggleVideoPlayPause);
  if (dom.vbarStop) dom.vbarStop.addEventListener('click', stopVideoAnalysis);
  if (dom.vbarProgress) dom.vbarProgress.addEventListener('input', seekVideoProgress);
  dom.btnCamera.addEventListener('click', toggleCamera);
  dom.modalClose.addEventListener('click', closeAlertModal);
  document.getElementById('btnClearAlerts').addEventListener('click', clearAlerts);
  
  // Close modal on backdrop click
  dom.alertModal.addEventListener('click', (e) => {
    if (e.target === dom.alertModal) closeAlertModal();
  });
}

function startClock() {
  setInterval(() => {
    dom.headerTime.textContent = new Date().toLocaleTimeString('vi-VN');
  }, 1000);
}

async function checkBackendStatus() {
  try {
    const resp = await fetch(`${CONFIG.API_BASE}/status`, { signal: AbortSignal.timeout(3000) });
    if (resp.ok) {
      const data = await resp.json();
      setStatus('online', `Kết nối – ${data.mode}`);
      dom.modeLabel.textContent = data.mode;
    }
  } catch (e) {
    setStatus('error', 'Backend offline');
    dom.modeLabel.textContent = 'Offline';
  }
}

// ─── Status ─────────────────────────────────────────────────────────────────
function setStatus(type, text) {
  dom.statusDot.className = `status-dot ${type}`;
  dom.statusText.textContent = text;
}

// ─── Demo Mode ───────────────────────────────────────────────────────────────
function toggleDemo() {
  if (state.mode === 'demo') {
    stopDemo();
  } else {
    stopAll();
    startDemo();
  }
}

function startDemo() {
  state.mode = 'demo';
  if (dom.btnDemo) {
    dom.btnDemo.textContent = '⏹ Stop Demo';
    dom.btnDemo.classList.add('active');
  }
  hideOverlay();
  setStatus('demo', 'Demo đang chạy...');
  
  connectWebSocket(CONFIG.DEMO_WS, handleDemoMessage);
}

function stopDemo() {
  state.mode = 'idle';
  if (dom.btnDemo) {
    dom.btnDemo.textContent = '▶ Demo Mode';
    dom.btnDemo.classList.remove('active');
  }
  
  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }
  
  setStatus('online', 'Đã dừng');
  showOverlay();
  drawIdleFrame();
  checkBackendStatus();
}

// ─── Camera Mode ─────────────────────────────────────────────────────────────
async function toggleCamera() {
  if (state.mode === 'camera') {
    stopCamera();
  } else {
    stopAll();
    await startCamera();
  }
}

async function startCamera() {
  try {
    state.cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480, facingMode: 'environment' }
    });
    
    const video = document.createElement('video');
    video.srcObject = state.cameraStream;
    video.autoplay = true;
    video.playsInline = true;
    
    video.onloadedmetadata = () => {
      state.mode = 'camera';
      dom.btnCamera.textContent = '⏹ Stop Camera';
      dom.btnCamera.classList.add('active');
      hideOverlay();
      setStatus('online', 'Webcam đang chạy...');
      
      connectWebSocket(CONFIG.VIDEO_WS, handleVideoMessage);
      
      // Send frames at ~10fps
      state.videoInterval = setInterval(async () => {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
          dom.canvas.width = video.videoWidth || 640;
          dom.canvas.height = video.videoHeight || 480;
          ctx.drawImage(video, 0, 0);
          
          dom.canvas.toBlob(async (blob) => {
            if (!blob) return;
            const arrayBuf = await blob.arrayBuffer();
            const b64 = btoa(String.fromCharCode(...new Uint8Array(arrayBuf)));
            state.ws.send(JSON.stringify({ type: 'frame', data: b64 }));
          }, 'image/jpeg', 0.75);
        }
      }, 100);
    };
    
    video.play();
    
  } catch (err) {
    alert(`Không thể truy cập camera: ${err.message}`);
    setStatus('error', 'Camera không khả dụng');
  }
}

function stopCamera() {
  if (state.cameraStream) {
    state.cameraStream.getTracks().forEach(t => t.stop());
    state.cameraStream = null;
  }
  if (state.videoInterval) {
    clearInterval(state.videoInterval);
    state.videoInterval = null;
  }
  state.mode = 'idle';
  dom.btnCamera.textContent = '📷 Webcam';
  dom.btnCamera.classList.remove('active');
  setStatus('online', 'Camera đã dừng');
  showOverlay();
  drawIdleFrame();
}

// ─── File Upload (Ảnh) ───────────────────────────────────────────────────────
async function handleFileUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  
  stopAll();
  stopIdleAnimation();
  
  state.mode = 'upload';
  setStatus('online', '⏳ Đang phân tích hình ảnh trên màn hình...');
  hideOverlay();
  
  // Show loading indicator directly on central canvas
  const origW = 640;
  const origH = 480;
  dom.canvas.width = origW;
  dom.canvas.height = origH;
  ctx.fillStyle = '#0a0e1a';
  ctx.fillRect(0, 0, origW, origH);
  ctx.font = '600 16px Inter, sans-serif';
  ctx.fillStyle = '#38bdf8';
  ctx.textAlign = 'center';
  ctx.fillText('🔍 Đang phân tích tư thế & nguy cơ đuối nước...', origW / 2, origH / 2 - 10);
  ctx.font = '13px Inter, sans-serif';
  ctx.fillStyle = '#94a3b8';
  ctx.fillText('Chạy YOLOv8-Pose & mạng học sâu CNN-LSTM...', origW / 2, origH / 2 + 25);
  ctx.textAlign = 'left';
  
  // Send to API
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    const resp = await fetch(`${CONFIG.API_BASE}/detect/image`, { method: 'POST', body: formData });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    
    stopIdleAnimation();
    state.mode = 'upload';
    
    // Render processed image with skeletons directly onto central canvas
    const imgEl = new Image();
    imgEl.onload = () => {
      stopIdleAnimation();
      dom.canvas.width = imgEl.naturalWidth;
      dom.canvas.height = imgEl.naturalHeight;
      ctx.clearRect(0, 0, dom.canvas.width, dom.canvas.height);
      ctx.drawImage(imgEl, 0, 0);
      
      // Draw sleek on-canvas HUD header badge
      const numDet = data.detections ? data.detections.length : 0;
      if (numDet > 0) {
        drawCanvasHUD(`AI DETECTION: ${numDet} NGƯỜI PHÁT HIỆN`);
      } else {
        drawCanvasHUD(`AI SCAN: 0 PHÁT HIỆN`);
      }
    };
    imgEl.src = `data:image/jpeg;base64,${data.processed_image}`;
    
    // Update detections list & counters in sidebar
    updateDetections(data.detections || []);
    
    // Update alerts
    if (data.alerts && data.alerts.length > 0) {
      data.alerts.forEach(a => addAlertItem(a));
      showAlertModal(data.alerts[0]);
    }
    
    if (data.detections && data.detections.length > 0) {
      setStatus('online', `✅ Đã phân tích: Phát hiện ${data.detections.length} người`);
    } else {
      setStatus('online', `ℹ️ Đã quét xong: 0 người bơi trong khung hình`);
    }
    
  } catch (err) {
    setStatus('error', `Lỗi phân tích: ${err.message}`);
    console.error('Upload error:', err);
    ctx.fillStyle = '#ef4444';
    ctx.textAlign = 'center';
    ctx.fillText(`Lỗi: ${err.message}`, origW / 2, origH / 2);
    ctx.textAlign = 'left';
  }
  
  dom.fileInput.value = '';
}

async function loadSampleAndAnalyze(url, filename) {
  stopAll();
  stopIdleAnimation();
  
  state.mode = 'upload';
  setStatus('online', `⏳ Đang nạp & phân tích ${filename}...`);
  hideOverlay();
  
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Không tải được ảnh ${filename}`);
    const blob = await resp.blob();
    const file = new File([blob], filename, { type: 'image/jpeg' });
    
    const fakeEvent = { target: { files: [file], value: '' } };
    await handleFileUpload(fakeEvent);
  } catch (err) {
    console.error('Error loading sample image:', err);
    setStatus('error', `Lỗi tải ảnh mẫu: ${err.message}`);
  }
}

function testSampleImage() {
  loadSampleAndAnalyze('/static/samples/sample_drowning.jpg', 'sample_drowning.jpg');
}

// ─── Video Upload & Phân tích Trực tiếp: CHỜ LOAD HẾT FRAME RỒI MỚI PHÁT ─────
let isVideoCancelled = false;
let preanalyzedFrames = [];
let videoPlaybackTimer = null;
let currentFrameIdx = 0;
let isVideoPlaying = false;
let videoTotalDuration = 0;
let videoStepSec = 0.4;

function formatTime(sec) {
  if (isNaN(sec) || !isFinite(sec)) return '00:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
}

async function handleVideoFileUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  startPreloadAndAnalyzeVideo(URL.createObjectURL(file), file.name);
  dom.videoFileInput.value = '';
}

async function testSampleVideo() {
  startPreloadAndAnalyzeVideo('/static/samples/sample_pool_video.mp4', 'sample_pool_video.mp4');
}

function drawVideoLoadingScreen(current, total, timeSec, duration) {
  const w = dom.canvas.width || 640;
  const h = dom.canvas.height || 480;
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;

  ctx.save();
  // Nền tối công nghệ cao
  ctx.fillStyle = '#080d1a';
  ctx.fillRect(0, 0, w, h);

  // Hiệu ứng lưới nền nhẹ
  ctx.strokeStyle = 'rgba(56, 189, 248, 0.06)';
  ctx.lineWidth = 1;
  for (let x = 0; x < w; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
  }
  for (let y = 0; y < h; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }

  // Khung kính mờ trung tâm
  const pw = Math.min(520, w - 40);
  const ph = 240;
  const px = (w - pw) / 2;
  const py = (h - ph) / 2;

  ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
  ctx.strokeStyle = 'rgba(56, 189, 248, 0.5)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(px, py, pw, ph, 12);
  else ctx.rect(px, py, pw, ph);
  ctx.fill();
  ctx.stroke();

  // Biểu tượng động
  ctx.font = '34px serif';
  ctx.textAlign = 'center';
  ctx.fillText('⏳', w / 2, py + 48);

  // Tiêu đề
  ctx.font = '700 16px Inter, sans-serif';
  ctx.fillStyle = '#38bdf8';
  ctx.fillText('ĐANG NẠP & PHÂN TÍCH TOÀN BỘ KHUNG HÌNH VIDEO', w / 2, py + 82);

  // Phụ đề hướng dẫn
  ctx.font = '500 12px Inter, sans-serif';
  ctx.fillStyle = '#94a3b8';
  ctx.fillText('Chờ nạp xong toàn bộ frames để phát mượt mà, không giật lag...', w / 2, py + 106);

  // Thanh tiến trình
  const bx = px + 40;
  const by = py + 130;
  const bw = pw - 80;
  const bh = 14;

  ctx.fillStyle = 'rgba(30, 41, 59, 0.95)';
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(bx, by, bw, bh, 7);
  else ctx.rect(bx, by, bw, bh);
  ctx.fill();

  // Phần đã hoàn thành (Gradient Cyan - Blue)
  const fillW = Math.max(8, (bw * pct) / 100);
  const grad = ctx.createLinearGradient(bx, 0, bx + fillW, 0);
  grad.addColorStop(0, '#06b6d4');
  grad.addColorStop(1, '#3b82f6');
  ctx.fillStyle = grad;
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(bx, by, fillW, bh, 7);
  else ctx.rect(bx, by, fillW, bh);
  ctx.fill();

  // Phần trăm & Số frame
  ctx.font = '700 14px "JetBrains Mono", monospace';
  ctx.fillStyle = '#38bdf8';
  ctx.textAlign = 'left';
  ctx.fillText(`${pct}%`, bx, by + 34);

  ctx.textAlign = 'right';
  ctx.fillStyle = '#94a3b8';
  ctx.font = '500 12px Inter, sans-serif';
  ctx.fillText(`Khung hình: ${current}/${total} (${timeSec.toFixed(1)}s / ${duration.toFixed(1)}s)`, bx + bw, by + 34);

  // Ghi chú phía dưới
  ctx.textAlign = 'center';
  ctx.fillStyle = '#64748b';
  ctx.font = '11px Inter, sans-serif';
  ctx.fillText('Chạy YOLOv8-Pose bóc tách khớp xương & mạng CNN-LSTM tính rủi ro...', w / 2, py + 205);

  ctx.restore();
}

async function startPreloadAndAnalyzeVideo(videoSrc, title) {
  stopAll();
  stopIdleAnimation();
  isVideoCancelled = false;
  preanalyzedFrames = [];
  currentFrameIdx = 0;
  isVideoPlaying = false;

  state.mode = 'video';
  setStatus('online', `⏳ Đang nạp toàn bộ khung hình video: ${title}...`);
  hideOverlay();
  dom.videoPlayerBar.style.display = 'none';

  const video = dom.uploadedVideo;
  video.pause();
  video.src = videoSrc;
  video.load();

  try {
    await new Promise((resolve, reject) => {
      video.onloadedmetadata = () => resolve();
      video.onerror = (e) => reject(new Error('Không thể tải file video'));
      // Timeout 10s
      setTimeout(() => resolve(), 10000);
    });
  } catch (err) {
    setStatus('error', `Lỗi tải video: ${err.message}`);
    return;
  }

  const duration = video.duration || 5.0;
  videoTotalDuration = duration;
  const vw = video.videoWidth || 640;
  const vh = video.videoHeight || 480;
  dom.canvas.width = vw;
  dom.canvas.height = vh;

  // Lấy mẫu frame với mật độ phù hợp: ~15 đến 30 frames cho toàn bộ video
  // Đảm bảo thời gian chờ chỉ mất ~3-5 giây nhưng video phát cực kỳ mượt mà
  const stepSec = Math.max(0.3, Math.min(0.6, duration / 25));
  videoStepSec = stepSec;
  const timestamps = [];
  for (let t = 0; t < duration; t += stepSec) {
    timestamps.push(t);
  }
  if (timestamps.length === 0 || timestamps[timestamps.length - 1] < duration - 0.2) {
    timestamps.push(Math.max(0, duration - 0.1));
  }

  const total = timestamps.length;
  drawVideoLoadingScreen(0, total, 0, duration);

  // Tạo offscreen canvas để trích xuất frame Blob
  const offCanvas = document.createElement('canvas');
  offCanvas.width = vw;
  offCanvas.height = vh;
  const offCtx = offCanvas.getContext('2d');

  for (let i = 0; i < total; i++) {
    if (isVideoCancelled || state.mode !== 'video') {
      return;
    }

    const t = timestamps[i];

    // Chờ video chuyển đến đúng vị trí frame t
    await new Promise((resolve) => {
      let resolved = false;
      const onSeeked = () => {
        if (!resolved) {
          resolved = true;
          video.removeEventListener('seeked', onSeeked);
          resolve();
        }
      };
      video.addEventListener('seeked', onSeeked);
      video.currentTime = t;
      // Fallback timeout nếu sự kiện seeked chậm
      setTimeout(() => {
        if (!resolved) {
          resolved = true;
          video.removeEventListener('seeked', onSeeked);
          resolve();
        }
      }, 500);
    });

    // Vẽ frame lên offscreen canvas
    offCtx.drawImage(video, 0, 0, vw, vh);

    // Lấy Blob ảnh JPEG và gửi phân tích
    const blob = await new Promise((res) => offCanvas.toBlob(res, 'image/jpeg', 0.75));
    if (blob) {
      const formData = new FormData();
      formData.append('file', blob, `frame_${i}.jpg`);

      try {
        const resp = await fetch(`${CONFIG.API_BASE}/detect/image`, {
          method: 'POST',
          body: formData
        });
        if (resp.ok) {
          const data = await resp.json();
          preanalyzedFrames.push({
            idx: i,
            time: t,
            imageB64: data.processed_image,
            detections: data.detections || [],
            alerts: data.alerts || []
          });
        }
      } catch (err) {
        console.warn('Frame analysis error:', err);
      }
    }

    // Cập nhật thanh tiến trình Loading trên màn hình
    drawVideoLoadingScreen(i + 1, total, t, duration);
    setStatus('online', `⏳ Đang nạp & phân tích video: ${Math.round(((i + 1) / total) * 100)}% (${i + 1}/${total} frames)`);
  }

  if (isVideoCancelled || state.mode !== 'video' || preanalyzedFrames.length === 0) {
    return;
  }

  // ĐÃ HOÀN TẤT NẠP & PHÂN TÍCH 100% CÁC KHUNG HÌNH!
  setStatus('online', `✅ Đã phân tích xong ${preanalyzedFrames.length} khung hình! Đang phát video...`);
  dom.videoPlayerBar.style.display = 'flex';
  if (dom.btnUploadVideo) dom.btnUploadVideo.classList.add('active');

  // Khởi động phát video mượt mà
  currentFrameIdx = 0;
  displayPreanalyzedFrame(currentFrameIdx, duration);
  playPreanalyzedVideo(stepSec, duration);
}

function displayPreanalyzedFrame(idx, duration) {
  if (!preanalyzedFrames || preanalyzedFrames.length === 0) return;
  idx = Math.max(0, Math.min(preanalyzedFrames.length - 1, idx));
  currentFrameIdx = idx;
  const f = preanalyzedFrames[idx];

  // Vẽ ảnh đã xử lý lên màn hình trung tâm
  if (f.imageB64) {
    const imgEl = new Image();
    imgEl.onload = () => {
      if (state.mode === 'video') {
        ctx.clearRect(0, 0, dom.canvas.width, dom.canvas.height);
        ctx.drawImage(imgEl, 0, 0);
        drawCanvasHUD(`AI VIDEO: ${f.detections ? f.detections.length : 0} NGƯỜI | FRAME ${idx + 1}/${preanalyzedFrames.length}`);
      }
    };
    imgEl.src = `data:image/jpeg;base64,${f.imageB64}`;
  }

  // Cập nhật thanh thời gian và scrubber
  const dur = duration || videoTotalDuration || 1;
  dom.vbarProgress.value = (f.time / dur) * 100;
  dom.vbarTime.textContent = `${formatTime(f.time)} / ${formatTime(dur)}`;

  // Cập nhật danh sách người bơi, ô lưới và cảnh báo
  state.frameCount++;
  dom.frameCount.textContent = state.frameCount;
  updateDetections(f.detections || []);
  if (f.alerts && f.alerts.length > 0) {
    f.alerts.forEach(a => addAlertItem(a));
    showAlertModal(f.alerts[0]);
  }
}

function playPreanalyzedVideo(stepSec, duration) {
  if (videoPlaybackTimer) clearInterval(videoPlaybackTimer);
  isVideoPlaying = true;
  dom.vbarPlayPause.textContent = '⏸ Tạm dừng';

  const intervalMs = Math.round((stepSec || 0.4) * 1000);

  videoPlaybackTimer = setInterval(() => {
    if (!isVideoPlaying || state.mode !== 'video') return;

    currentFrameIdx++;
    if (currentFrameIdx >= preanalyzedFrames.length) {
      currentFrameIdx = 0; // Lặp lại video
    }
    displayPreanalyzedFrame(currentFrameIdx, duration);
  }, intervalMs);
}

function toggleVideoPlayPause() {
  if (!preanalyzedFrames || preanalyzedFrames.length === 0) return;
  if (isVideoPlaying) {
    isVideoPlaying = false;
    dom.vbarPlayPause.textContent = '▶ Tiếp tục';
    setStatus('online', 'Video đã tạm dừng');
  } else {
    isVideoPlaying = true;
    dom.vbarPlayPause.textContent = '⏸ Tạm dừng';
    setStatus('online', 'Đang phát video đã phân tích...');
  }
}

function seekVideoProgress(e) {
  if (!preanalyzedFrames || preanalyzedFrames.length === 0) return;
  const pct = parseFloat(e.target.value) / 100;
  const dur = videoTotalDuration || 1;
  const targetTime = pct * dur;

  // Tìm frame có thời gian gần nhất với vị trí tua
  let bestIdx = 0;
  let minDiff = 9999;
  preanalyzedFrames.forEach((f, i) => {
    const diff = Math.abs(f.time - targetTime);
    if (diff < minDiff) {
      minDiff = diff;
      bestIdx = i;
    }
  });

  displayPreanalyzedFrame(bestIdx, dur);
}

function stopVideoAnalysis() {
  isVideoCancelled = true;
  isVideoPlaying = false;
  if (videoPlaybackTimer) {
    clearInterval(videoPlaybackTimer);
    videoPlaybackTimer = null;
  }
  preanalyzedFrames = [];
  const video = dom.uploadedVideo;
  if (video) {
    video.pause();
    video.src = '';
  }
  dom.videoPlayerBar.style.display = 'none';
  if (dom.btnUploadVideo) dom.btnUploadVideo.classList.remove('active');
  state.mode = 'idle';
  setStatus('online', 'Đã dừng phân tích video');
  showOverlay();
  startIdleAnimation();
}

function drawCanvasHUD(text) {
  ctx.save();
  ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
  ctx.fillRect(10, 10, 240, 28);
  ctx.strokeStyle = 'rgba(56, 189, 248, 0.5)';
  ctx.lineWidth = 1;
  ctx.strokeRect(10, 10, 240, 28);
  ctx.fillStyle = '#38bdf8';
  ctx.font = '600 12px Inter, sans-serif';
  ctx.fillText(text, 20, 28);
  ctx.restore();
}

// ─── WebSocket ───────────────────────────────────────────────────────────────
function connectWebSocket(url, messageHandler) {
  if (state.ws) { state.ws.close(); }
  
  try {
    state.ws = new WebSocket(url);
    
    state.ws.onopen = () => {
      console.log('[WS] Connected to', url);
      setStatus('online', 'WebSocket kết nối');
    };
    
    state.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        messageHandler(data);
      } catch (e) {
        console.error('WS parse error:', e);
      }
    };
    
    state.ws.onerror = (e) => {
      console.error('[WS] Error:', e);
      setStatus('error', 'WS lỗi kết nối');
    };
    
    state.ws.onclose = () => {
      console.log('[WS] Disconnected');
      if (state.mode !== 'idle') {
        setStatus('error', 'WS ngắt kết nối');
        // Reconnect after 2s
        setTimeout(() => {
          if (state.mode !== 'idle') connectWebSocket(url, messageHandler);
        }, 2000);
      }
    };
  } catch (e) {
    setStatus('error', 'Không thể kết nối');
  }
}

function handleDemoMessage(data) {
  if (data.type === 'demo_frame') {
    renderFrame(data.frame);
    updateDetections(data.detections || []);
    updateStats(data.stats || {}, data.frame_count || 0);
    processNewAlerts(data.new_alerts || []);
    updateFPS();
  }
}

function handleVideoMessage(data) {
  if (data.type === 'result') {
    renderFrame(data.frame);
    updateDetections(data.detections || []);
    updateStats(data.stats || {}, data.frame_count || 0);
    processNewAlerts(data.new_alerts || []);
    updateFPS();
  }
}

// ─── Rendering ───────────────────────────────────────────────────────────────
function renderFrame(b64) {
  const img = new Image();
  img.onload = () => {
    dom.canvas.width = img.naturalWidth;
    dom.canvas.height = img.naturalHeight;
    ctx.drawImage(img, 0, 0);
  };
  img.src = `data:image/jpeg;base64,${b64}`;
  state.frameCount++;
  dom.frameCount.textContent = state.frameCount;
}

let idleAnimId = null;

function stopIdleAnimation() {
  if (idleAnimId) {
    cancelAnimationFrame(idleAnimId);
    idleAnimId = null;
  }
}

function startIdleAnimation() {
  stopIdleAnimation();
  if (state.mode === 'idle') {
    drawIdleFrame();
  }
}

function drawIdleFrame() {
  if (state.mode !== 'idle') {
    stopIdleAnimation();
    return;
  }
  const w = dom.canvas.width, h = dom.canvas.height;
  ctx.clearRect(0, 0, w, h);
  
  // Dark background
  const grad = ctx.createLinearGradient(0, 0, w, h);
  grad.addColorStop(0, '#0a0e1a');
  grad.addColorStop(1, '#141c2f');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
  
  // Water ripple animation
  const t = Date.now() / 1000;
  for (let i = 0; i < 5; i++) {
    const r = 60 + i * 40 + Math.sin(t + i) * 10;
    ctx.beginPath();
    ctx.arc(w/2, h/2, r, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(59,130,246,${0.15 - i * 0.02})`;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
  
  // Emoji + text
  ctx.font = '48px serif';
  ctx.textAlign = 'center';
  ctx.fillText('🏊', w/2, h/2 - 20);
  
  ctx.font = '500 14px Inter, sans-serif';
  ctx.fillStyle = 'rgba(148,163,184,0.7)';
  ctx.fillText('AI Drowning Detection System', w/2, h/2 + 35);
  ctx.font = '12px Inter, sans-serif';
  ctx.fillStyle = 'rgba(71,85,105,0.8)';
  ctx.fillText('Nhóm 7 – PPLNCKH 2026', w/2, h/2 + 55);
  
  ctx.textAlign = 'left';
  if (state.mode === 'idle') {
    idleAnimId = requestAnimationFrame(drawIdleFrame);
  }
}

// ─── UI Updates ───────────────────────────────────────────────────────────────
function updateDetections(detections) {
  dom.detectionBadge.textContent = detections.length;
  dom.personCount.textContent = detections.length;
  
  let safe = 0, warn = 0, danger = 0;
  const zoneStatus = {};
  
  detections.forEach(d => {
    if (d.risk_score >= CONFIG.DANGER_THRESHOLD) danger++;
    else if (d.risk_score >= CONFIG.WARN_THRESHOLD) warn++;
    else safe++;
    
    const cell = d.cell || 'A1';
    if (!zoneStatus[cell] || zoneRank(d.status) > zoneRank(zoneStatus[cell])) {
      zoneStatus[cell] = d.status;
    }
  });
  
  state.safeCount   = safe;
  state.warnCount   = warn;
  state.dangerCount = danger;
  
  dom.safeCount.textContent   = safe;
  dom.warnCount.textContent   = warn;
  dom.dangerCount.textContent = danger;
  
  // Update zone grid
  document.querySelectorAll('.zone-cell').forEach(cell => {
    cell.className = 'zone-cell safe';
  });
  
  Object.entries(zoneStatus).forEach(([cell, status]) => {
    const el = document.getElementById(`zone-${cell}`);
    if (el) {
      el.className = `zone-cell ${statusClass(status)}`;
    }
  });
  
  // Update detection list
  if (detections.length === 0) {
    dom.detectionList.innerHTML = `
      <div class="empty-state" style="padding: 16px 12px; text-align: center; color: var(--text-muted);">
        <div style="font-size: 22px; margin-bottom: 6px;">ℹ️</div>
        <div style="font-weight: 600; color: var(--text-primary); font-size: 13px; margin-bottom: 4px;">Đã quét toàn bộ khung hình</div>
        <div style="font-size: 11px; line-height: 1.4; color: var(--text-secondary);">0 người bơi được phát hiện (khung cảnh trống hoặc bị che khuất).</div>
      </div>
    `;
    return;
  }
  
  dom.detectionList.innerHTML = detections.map(d => {
    const cls = statusClass(d.status);
    const pct = (d.risk_score * 100).toFixed(0);
    return `
      <div class="detection-item">
        <div class="det-indicator ${cls}"></div>
        <div class="det-info">
          <div class="det-name">Người #${d.id} – ${d.cell || '?'}</div>
          <div class="det-sub">${d.risk_factors && d.risk_factors.length > 0
            ? d.risk_factors.slice(0,2).join(' · ')
            : 'Không có dấu hiệu bất thường'}</div>
          <div class="risk-bar">
            <div class="risk-fill ${cls}" style="width:${pct}%"></div>
          </div>
        </div>
        <div class="det-risk ${cls}">${pct}%</div>
      </div>
    `;
  }).join('');
}

function updateStats(stats, frameCount) {
  if (stats.total_alerts !== undefined) {
    state.totalAlerts = stats.total_alerts;
    dom.totalAlerts.textContent = stats.total_alerts;
  }
  
  if (stats.mode) {
    dom.modeLabel.textContent = stats.mode;
  }
  
  dom.footerStats.textContent = `Tổng frames: ${frameCount} | Detections: ${stats.total_detections || 0} | Cảnh báo: ${stats.total_alerts || 0}`;
}

function processNewAlerts(alerts) {
  if (!alerts || alerts.length === 0) return;
  
  alerts.forEach(alert => {
    addAlertItem(alert);
    state.totalAlerts++;
    dom.totalAlerts.textContent = state.totalAlerts;
  });
  
  // Show modal for first alert (anti-spam: max 1 modal per 15s)
  const now = Date.now();
  if (now - state.lastAlertModalTime > 15000) {
    state.lastAlertModalTime = now;
    showAlertModal(alerts[0]);
  }
}

function addAlertItem(alert) {
  state.alerts.unshift(alert);
  if (state.alerts.length > 50) state.alerts.pop();
  
  const emptyState = dom.alertList.querySelector('.empty-state');
  if (emptyState) emptyState.remove();
  
  const item = document.createElement('div');
  item.className = 'alert-item';
  item.id = `alert-${alert.id}`;
  item.innerHTML = `
    <div class="alert-header">
      <span class="alert-zone">🆘 ${alert.zone || alert.cell} – ${alert.status}</span>
      <span class="alert-time">${alert.time}</span>
    </div>
    <div class="alert-detail">
      Người #${alert.person_id} · Độ tin cậy: <strong style="color: var(--red)">${alert.confidence}%</strong>
    </div>
  `;
  
  dom.alertList.insertBefore(item, dom.alertList.firstChild);
  
  // Keep max 20 items visible
  const items = dom.alertList.querySelectorAll('.alert-item');
  if (items.length > 20) items[items.length - 1].remove();
}

function updateFPS() {
  const now = performance.now();
  state.fpsBuffer.push(now);
  
  // Keep only last 30 frames for FPS calc
  if (state.fpsBuffer.length > CONFIG.FPS_WINDOW) {
    state.fpsBuffer.shift();
  }
  
  if (state.fpsBuffer.length >= 2) {
    const elapsed = (state.fpsBuffer[state.fpsBuffer.length - 1] - state.fpsBuffer[0]) / 1000;
    const fps = (state.fpsBuffer.length - 1) / elapsed;
    dom.fpsDisplay.textContent = fps.toFixed(1);
  }
}

// ─── Alert Modal ─────────────────────────────────────────────────────────────
function showAlertModal(alert) {
  dom.modalBody.innerHTML = `
    <strong>${alert.zone || alert.cell}</strong> – Phát hiện người có nguy cơ đuối nước!<br>
    Độ tin cậy: <strong style="color:var(--red)">${alert.confidence}%</strong><br>
    Thời gian: ${alert.time}
  `;
  dom.alertModal.style.display = 'flex';
  
  // Auto-close after 8s
  setTimeout(closeAlertModal, 8000);
  
  // Play alert sound
  playAlertSound();
}

function closeAlertModal() {
  dom.alertModal.style.display = 'none';
}

function playAlertSound() {
  try {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    
    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(880, audioCtx.currentTime);
    oscillator.frequency.setValueAtTime(660, audioCtx.currentTime + 0.2);
    oscillator.frequency.setValueAtTime(880, audioCtx.currentTime + 0.4);
    
    gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.8);
    
    oscillator.start(audioCtx.currentTime);
    oscillator.stop(audioCtx.currentTime + 0.8);
  } catch (e) {
    // Audio not available, silent
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
function clearAlerts() {
  state.alerts = [];
  dom.alertList.innerHTML = '<div class="empty-state">Chưa có cảnh báo nào</div>';
}

function showOverlay() { dom.videoOverlay.classList.remove('hidden'); }
function hideOverlay() { dom.videoOverlay.classList.add('hidden'); }

function stopAll() {
  if (state.mode === 'demo') stopDemo();
  if (state.mode === 'camera') stopCamera();
  if (state.mode === 'video') stopVideoAnalysis();
  stopIdleAnimation();
  state.mode = 'idle';
}

function statusClass(status) {
  if (!status) return 'safe';
  if (status.includes('NGUY HIỂM') || status.includes('danger')) return 'danger';
  if (status.includes('CẢNH BÁO') || status.includes('warn')) return 'warn';
  return 'safe';
}

function zoneRank(status) {
  const cls = statusClass(status);
  return cls === 'danger' ? 2 : cls === 'warn' ? 1 : 0;
}

function riskColor(risk) {
  if (risk >= 0.5) return 'var(--danger-color, #ef4444)';
  if (risk >= 0.3) return 'var(--warn-color, #f59e0b)';
  return 'var(--safe-color, #10b981)';
}

// ─── Bootstrap ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
