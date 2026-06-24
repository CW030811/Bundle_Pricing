@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 当前工作目录: %CD%
echo 设置 UTF-8 编码完成
echo.
echo Legacy wrapper notice:
echo   This script no longer uses conda environment pyg311 by default.
echo   Preferred current workflow is:
echo   python src\test\LS_Path_Test.py
echo.
echo 开始运行 src\test\LS_Path_Test.py...
echo ================================================================================
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe src\test\LS_Path_Test.py
) else (
    python src\test\LS_Path_Test.py
)
if errorlevel 1 (
    echo.
    echo 实验执行出错
    pause
    exit /b 1
)
echo.
echo 实验完成！
pause

