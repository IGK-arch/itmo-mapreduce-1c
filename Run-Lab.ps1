param(
    [ValidateSet('check','init-storage','list-storage','setup-duckdb','audit','upload','benchmark','fault','verify','analyze','test','report')]
    [string]$Action='check'
)
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$taskPythonCandidates = @(
    (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
    (Join-Path $PSScriptRoot '..\lab\.venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)
$taskPythonPath = $taskPythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $taskPythonPath) { $taskPythonPath=(Get-Command python.exe -ErrorAction Stop).Source }
switch ($Action) {
    'setup-duckdb' { & $taskPythonPath (Join-Path $PSScriptRoot 'scripts\setup_duckdb.py') }
    'audit' { & $taskPythonPath (Join-Path $PSScriptRoot 'scripts\prepare_data.py') audit }
    'upload' { & $taskPythonPath (Join-Path $PSScriptRoot 'scripts\prepare_data.py') upload }
    'benchmark' { & $taskPythonPath (Join-Path $PSScriptRoot 'scripts\benchmark.py') --repeats 3 }
    'fault' { & $taskPythonPath (Join-Path $PSScriptRoot 'scripts\benchmark.py') --fault-only }
    'verify' { & $taskPythonPath (Join-Path $PSScriptRoot 'scripts\verify_results.py') }
    'analyze' { & $taskPythonPath (Join-Path $PSScriptRoot 'scripts\analyze.py') }
    'test' { & $taskPythonPath -m unittest discover -s (Join-Path $PSScriptRoot 'tests') -v }
    'report' { & $taskPythonPath (Join-Path $PSScriptRoot 'scripts\build_report.py') }
    default { & $taskPythonPath (Join-Path $PSScriptRoot 'scripts\manage_storage.py') $Action }
}
if ($LASTEXITCODE -ne 0) { throw "Ошибка команды $Action, код $LASTEXITCODE" }

