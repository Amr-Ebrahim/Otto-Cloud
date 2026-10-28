@echo off
cd /d "%~dp0"
echo === Otto Cloud setup ===
py -3.11 -m venv .venv
if errorlevel 1 (
  echo.
  echo Python 3.11 was not found. Install it from https://www.python.org/downloads/ and run setup.bat again.
  pause
  exit /b 1
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -c "import openwakeword.utils as u; u.download_models()"
if not exist .env copy .env.example .env
echo.
echo Done! Open .env, add your API keys, then double-click start_otto.bat
pause
