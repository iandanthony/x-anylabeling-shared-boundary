param(
    [string]$Python = '',
    [string]$Name = 'X-AnyLabeling Shared Boundary'
)
$ErrorActionPreference = 'Stop'
if (-not $Python) { $Python = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe' }
if (-not (Test-Path -LiteralPath $Python)) { throw 'pythonw.exe was not found; install first or pass -Python.' }
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopPath "$Name.lnk"
if (Test-Path -LiteralPath $shortcutPath) { throw 'A shortcut with this name exists. Choose another -Name.' }
$shellObject = New-Object -ComObject WScript.Shell
$shortcutObject = $shellObject.CreateShortcut($shortcutPath)
$shortcutObject.TargetPath = (Resolve-Path -LiteralPath $Python).Path
$shortcutObject.Arguments = '"' + (Join-Path $PSScriptRoot 'launch.py') + '"'
$shortcutObject.WorkingDirectory = $PSScriptRoot
$shortcutObject.Description = 'X-AnyLabeling 4.0.6 with shared-boundary editing'
$shortcutObject.Save()
Write-Host "Created: $shortcutPath"
