# PowerShell script to run LS_Path_Test.py via the current src/ layout
# Set UTF-8 encoding for proper Chinese character display
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Set the working directory to the script's directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

Write-Host "当前工作目录: $scriptDir" -ForegroundColor Green
Write-Host "设置 UTF-8 编码完成" -ForegroundColor Green

Write-Host "Legacy wrapper notice: this script now forwards to src/test/LS_Path_Test.py" -ForegroundColor Yellow
Write-Host "Preferred current workflow: activate .venv and run python src/test/LS_Path_Test.py" -ForegroundColor Yellow

# Run the Python script
Write-Host "`n开始运行 src/test/LS_Path_Test.py..." -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan

$pythonCmd = $null
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonCmd = $venvPython
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} else {
    Write-Host "错误: 未找到可用 Python，请先创建 .venv 或配置 PATH" -ForegroundColor Red
    exit 1
}

& $pythonCmd "src/test/LS_Path_Test.py"

$exitCode = $LASTEXITCODE
if ($exitCode -eq 0) {
    Write-Host "`n实验完成！" -ForegroundColor Green
} else {
    Write-Host "`n实验执行出错，退出代码: $exitCode" -ForegroundColor Red
}

# Keep the console open
Write-Host "`n按任意键退出..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

