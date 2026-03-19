@echo off
REM Launch script for Chord Harmony Generator web UI
cd /d "%~dp0"

if not exist ".venv" (
    echo Virtual environment not found. Running setup first...
    call setup_harmony_app.bat
)

echo Activating virtual environment...
call ".venv\Scripts\activate.bat"

echo Starting web server...
echo Opening your default browser at http://127.0.0.1:5001/ ...
start "" "http://127.0.0.1:5001/"
echo.
python web_app.py

