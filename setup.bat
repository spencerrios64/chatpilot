@echo off
rem chatpilot setup: checks Python and Ollama, then downloads the default model (about 9 GB).
where python >nul 2>nul || (echo Python is missing. Install it from https://python.org and run this again. & pause & exit /b 1)
where ollama >nul 2>nul || (echo Ollama is missing. Install it from https://ollama.com and run this again. & pause & exit /b 1)
echo Downloading the model. This can take a while...
ollama pull hf.co/RootMonsteR/Qwen3-14B-Abliterated-GGUF:Q4_K_M
echo.
echo Ready. Open a terminal in the folder you want the AI to work in and try:
echo   python "%~dp0chatpilot.py" "list the 10 biggest files here"
pause
