@echo off
setlocal
REM ============================================================================
REM  ติดตั้ง XAUUSD News Monitor เป็น Windows Service ด้วย NSSM
REM  ----------------------------------------------------------------------------
REM  ก่อนรัน:
REM    1) ติดตั้ง Python + สร้าง venv + pip install -r requirements.txt แล้ว
REM    2) ก๊อป .env.example เป็น .env และใส่ค่า secret แล้ว
REM    3) มี nssm.exe ใน PATH (โหลด win64 จาก https://nssm.cc/download
REM       แล้ววางไว้ใน C:\Windows\System32)
REM    4) คลิกขวาไฟล์นี้ -> "Run as administrator"
REM ============================================================================

REM ---- แก้ 2 ค่านี้ให้ตรงกับเครื่องคุณ ----
set "PROJECT_DIR=C:\news_gold"
set "SERVICE_NAME=XauusdNews"

set "PY=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "SCRIPT=%PROJECT_DIR%\main.py"

if not exist "%PY%" (
  echo [ERROR] ไม่พบ %PY%
  echo         สร้าง venv ก่อน:  python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
if not exist "%PROJECT_DIR%\.env" (
  echo [ERROR] ไม่พบ %PROJECT_DIR%\.env  -- copy .env.example .env แล้วใส่ secret ก่อน
  exit /b 1
)
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

echo กำลังติดตั้ง service "%SERVICE_NAME%" ...
nssm install %SERVICE_NAME% "%PY%" "%SCRIPT%"
nssm set %SERVICE_NAME% AppDirectory "%PROJECT_DIR%"
nssm set %SERVICE_NAME% AppStdout "%PROJECT_DIR%\logs\out.log"
nssm set %SERVICE_NAME% AppStderr "%PROJECT_DIR%\logs\err.log"
nssm set %SERVICE_NAME% AppRotateFiles 1
nssm set %SERVICE_NAME% AppRotateBytes 5242880
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm set %SERVICE_NAME% AppThrottle 10000
nssm set %SERVICE_NAME% AppExit Default Restart
nssm start %SERVICE_NAME%

echo.
echo ====================================================
echo  เสร็จแล้ว!
echo   ดูสถานะ : nssm status %SERVICE_NAME%
echo   ดู log  : type "%PROJECT_DIR%\logs\out.log"
echo ====================================================
endlocal
