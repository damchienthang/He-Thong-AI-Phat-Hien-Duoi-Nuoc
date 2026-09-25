@echo off
title AI Drowning Detection - Nhom 7
color 0B
echo.
echo  =============================================================
echo    HE THONG PHAT HIEN DUOI NUOC THONG MINH - NHOM 7
echo  =============================================================
echo.
cd /d "%~dp0WebDemo\backend"
echo  Dang khoi dong server tai http://localhost:8000 ...
timeout /t 2 /nobreak >nul
start http://localhost:8000
if exist "C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe" (
    "C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
) else (
    python -m uvicorn main:app --host 0.0.0.0 --port 8000
)
pause
