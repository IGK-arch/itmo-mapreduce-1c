param([ValidateSet('compute','verify')][string]$Action='compute')
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
Set-Location -LiteralPath $PSScriptRoot
$Host.UI.RawUI.WindowTitle="ЛР3 | MapReduce и DuckDB | $Action"
$taskPythonPath=Join-Path $PSScriptRoot '..\lab\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPythonPath)) {
    $taskPythonPath=(Get-Command python.exe -ErrorAction Stop).Source
}
Write-Host "Команда запуска: .\Show-Run.ps1 $Action" -ForegroundColor Cyan
& $taskPythonPath (Join-Path $PSScriptRoot 'scripts\demo_terminal.py') $Action
if ($LASTEXITCODE -ne 0) { throw "Расчёт завершился с ошибкой: $LASTEXITCODE" }
