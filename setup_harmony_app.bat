@echo off
REM Setup script for Chord Harmony Generator (creates venv and installs deps)
cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating virtual environment...
call ".venv\Scripts\activate.bat"

echo Upgrading pip and installing requirements...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Setup complete. You can now run:
echo   launch_harmony_web.bat   ^(web GUI^)
echo   python main.py           ^(CLI^)
echo.
pause

