@echo off
REM รันทดสอบแบบ foreground (กด Ctrl+C เพื่อหยุด) ก่อนติดตั้งเป็น service
REM ดับเบิลคลิกได้เลย -- จะ cd ไปโฟลเดอร์โปรเจกต์ให้อัตโนมัติ

cd /d "%~dp0..\.."

if not exist ".venv\Scripts\python.exe" (
  echo [!] ยังไม่มี venv -- สร้างก่อนด้วย:
  echo     python -m venv .venv
  echo     .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
if not exist ".env" (
  echo [!] ยังไม่มีไฟล์ .env -- ก๊อปจากตัวอย่างก่อน:  copy .env.example .env
  pause
  exit /b 1
)

".venv\Scripts\python.exe" main.py
pause
