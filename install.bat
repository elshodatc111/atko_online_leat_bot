@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   ATKO Lead platforma - o'rnatish
echo ============================================

where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py -3.14
) else (
    set PY=python
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Virtual muhit yaratilmoqda...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo XATO: Python 3.14 topilmadi. https://www.python.org dan o'rnating.
        pause
        exit /b 1
    )
)

echo [2/3] Kutubxonalar o'rnatilmoqda...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo XATO: kutubxonalarni o'rnatib bo'lmadi. Internetni tekshiring.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [3/3] .env fayli yaratilmoqda - uni to'ldiring va saqlang!
    copy ".env.example" ".env" >nul
    notepad ".env"
) else (
    echo [3/3] .env fayli mavjud.
)

echo.
echo Tayyor! Endi start.bat ni ishga tushiring.
pause
