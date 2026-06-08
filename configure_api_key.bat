@echo off
setlocal EnableDelayedExpansion
if not exist .env copy .env.example .env >nul
set /p OPENAIKEY=Paste your OpenAI API key here, then press Enter: 
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='.env'; $key=$env:OPENAIKEY; $txt=Get-Content $p -Raw; if($txt -match 'OPENAI_API_KEY='){$txt=$txt -replace 'OPENAI_API_KEY=.*','OPENAI_API_KEY='+$key}else{$txt += \"`nOPENAI_API_KEY=$key\"}; if($txt -match 'OPENAI_MODEL='){$txt=$txt -replace 'OPENAI_MODEL=.*','OPENAI_MODEL=gpt-5-nano'}else{$txt += \"`nOPENAI_MODEL=gpt-5-nano\"}; Set-Content -Path $p -Value $txt -Encoding UTF8"
echo.
echo Saved OPENAI_API_KEY and OPENAI_MODEL=gpt-5-nano to .env on this computer only.
pause
