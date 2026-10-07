param(
    [string]$Python = '',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$AppArguments
)
$ErrorActionPreference = 'Stop'
if (-not $Python) { $Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Python was not found. Install first, or use -Python with the full path to your existing environment.'
}
& $Python (Join-Path $PSScriptRoot 'launch.py') @AppArguments
if ($LASTEXITCODE -ne 0) { throw 'Application exited with an error; inspect the output above.' }
