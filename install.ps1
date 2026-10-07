param(
    [ValidateSet('cpu', 'gpu')][string]$Backend = 'cpu',
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$requirementsPath = Join-Path $PSScriptRoot "requirements-$Backend.txt"
$environmentPath = Join-Path $PSScriptRoot '.venv'
if (Test-Path -LiteralPath $environmentPath) {
    throw 'The .venv directory already exists. Use the manual update instructions or a fresh checkout.'
}
& $Python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Use Python 3.12 for the documented environment"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 check failed.' }
& $Python -m venv $environmentPath
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
$environmentPython = Join-Path $environmentPath 'Scripts\python.exe'
& $environmentPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip update failed.' }
& $environmentPython -m pip install -r $requirementsPath
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; inspect the error above.' }
& $environmentPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
Write-Host 'Installation complete. Start with: .\start.ps1'
