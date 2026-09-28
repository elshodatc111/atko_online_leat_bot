@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Avval install.bat ni ishga tushiring!
    pause
    exit /b 1
)
if not exist ".env" (
    echo .env fayli topilmadi. install.bat ni ishga tushiring.
    pause
    exit /b 1
)
echo ATKO Lead platforma ishga tushmoqda...
echo Panel: http://localhost:8000   (to'xtatish: Ctrl+C)
start "" "http://localhost:8000"
".venv\Scripts\python.exe" run.py
pause
