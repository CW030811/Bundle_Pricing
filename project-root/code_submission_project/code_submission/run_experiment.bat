@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Legacy wrapper notice:
echo   This script now forwards to src\test\test_FCP_LS.py.
echo   Preferred current workflow is to activate .venv and run:
echo   python src\test\test_FCP_LS.py
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe src\test\test_FCP_LS.py
) else (
    python src\test\test_FCP_LS.py
)
pause
