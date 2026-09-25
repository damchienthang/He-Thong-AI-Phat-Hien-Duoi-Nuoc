@echo off
title AI Drowning Detection - Nhom 7
color 0B
echo.
echo  =============================================================
echo    HE THONG PHAT HIEN DUOI NUOC THONG MINH - NHOM 7
echo    PPLNCKH 2026
echo  =============================================================
echo.
echo  [1/3] Kiem tra thu vien...
python -c "import fastapi, uvicorn, cv2; print('  OK: FastAPI, uvicorn, OpenCV')" 2>nul
python -c "import ultralytics; print('  OK: YOLOv8/Ultralytics')" 2>nul
echo.
echo  [2/3] Khoi dong Backend API...
echo  URL: http://localhost:8000
echo  WebSocket Demo: ws://localhost:8000/ws/demo
echo.
cd /d "%~dp0backend"
start /B python -m uvicorn main:app --host 0.0.0.0 --port 8000

echo  [3/3] Doi server khoi dong (5 giay)...
timeout /t 5 /nobreak >nul

echo.
echo  Mo trinh duyet...
start http://localhost:8000

echo.
echo  Server dang chay tai: http://localhost:8000
echo  Nhan Ctrl+C de dung server
echo.
pause
