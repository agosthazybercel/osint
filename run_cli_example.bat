@echo off
call .venv\Scripts\activate
python cli.py "Agosthazy Bercel" --mode person --target-type self --context "Budapesti Piarista Gimnazium" --lawful-use --no-ai
pause
