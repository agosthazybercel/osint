@echo off
call .venv\Scripts\activate
python -c "from deepsearch_core.config import settings; print('OPENAI_MODEL=', settings.openai_model); print('OPENAI_API_KEY set=', bool(settings.openai_api_key))"
pause
