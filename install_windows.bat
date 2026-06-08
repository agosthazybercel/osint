@echo off
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Installed. Edit .env if you want OpenAI/Brave/SerpAPI keys.
echo Run web UI with: run_web.bat
pause
