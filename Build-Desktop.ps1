param([string]$Output = 'desktop-dist')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$desktopOutput = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Output))
if ($desktopOutput -notin @((Join-Path $PSScriptRoot 'desktop-dist'),(Join-Path $PSScriptRoot 'desktop-next'))) { throw 'Unexpected desktop build output directory.' }
$desktopWork = Join-Path $PSScriptRoot '.work\desktop-build'
New-Item -ItemType Directory -Path $desktopWork -Force | Out-Null
.venv\Scripts\python.exe -m PyInstaller --noconfirm --onedir --windowed --name LightningFlow --icon (Join-Path $PSScriptRoot 'assets\lightningflow.ico') --version-file (Join-Path $PSScriptRoot 'assets\version-info.txt') --collect-data customtkinter --exclude-module numpy --exclude-module sounddevice --exclude-module ctranslate2 --exclude-module onnxruntime --exclude-module lightningflow.app --exclude-module lightningflow.asr --exclude-module lightningflow.win32 --exclude-module lightningflow.desktop.worker --distpath $desktopOutput --workpath $desktopWork --specpath $desktopWork desktop_main.py
if ($LASTEXITCODE) { throw 'Desktop executable build failed' }
$desktopRelease = Join-Path $desktopOutput 'LightningFlow'
New-Item -ItemType Directory -Path (Join-Path $desktopRelease 'engine\lightningflow') -Force | Out-Null
$desktopSourceRoot = (Join-Path $PSScriptRoot 'lightningflow')
Get-ChildItem -LiteralPath $desktopSourceRoot -Recurse -File | Where-Object { $_.Extension -ne '.pyc' -and $_.FullName -notmatch '\\__pycache__\\' } | ForEach-Object {
    $desktopRelative = $_.FullName.Substring($desktopSourceRoot.Length).TrimStart('\')
    $desktopDestination = Join-Path (Join-Path $desktopRelease 'engine\lightningflow') $desktopRelative
    New-Item -ItemType Directory -Path (Split-Path -Parent $desktopDestination) -Force | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $desktopDestination -Force
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'assets') -Destination $desktopRelease -Recurse -Force
foreach ($desktopFile in @('runtime-requirements.txt','Setup-Runtime.ps1','Install-LightningFlow.ps1','Uninstall-LightningFlow.ps1','Uninstall-LightningFlow.vbs','LICENSE','LICENSE_NOTICES.md','README.md','DESKTOP.md','DESKTOP_VALIDATION.md','ARCHITECTURE.md','INSTALLATION.md','TROUBLESHOOTING.md','MODEL_COMPARISON.md','PERFORMANCE.md','DESIGN_SYSTEM.md','UI_UPDATE.md','TEST_100.md','SHORTCUT_UPDATE.md','PERSONALIZATION.md','DECODER_FIX.md','APP_INSERTION_TEST.md','FIXES_0.5.0.md','FIXES_0.6.0.md','PRIVACY.md','SECURITY.md','CONTRIBUTING.md','CHANGELOG.md','ROADMAP.md')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $desktopFile) -Destination $desktopRelease -Force
}
$desktopEvidence = Join-Path $desktopRelease 'results'
New-Item -ItemType Directory -Path $desktopEvidence -Force | Out-Null
foreach ($desktopPattern in @('soak-100-*.json','log-paging-*.json','soak-proof-*.json','ctrl-win-*.json','personalization-*.json','personalized-pipeline-*.json','rtx-*.json','decoder-*.json','control-path-*.json','app-insertion-*.json','preview-latency-*.json','navigation-cache-*.json','accessibility-long-*.json','animation-0.5.0.json','desktop-integration-0.5.0.json','release-0.5.0.json','animation-0.6.0.json','desktop-integration-0.6.0.json','long-recordings-0.6.0.json','queue-recovery-0.6.0.json','frozen-self-check-0.6.0.json')) {
    Get-ChildItem -Path (Join-Path $PSScriptRoot ('results\' + $desktopPattern)) -File -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $desktopEvidence -Force
    }
}
.venv\Scripts\python.exe scripts\collect_licenses.py $desktopRelease
if ($LASTEXITCODE) { throw 'Could not collect dependency notices' }
$desktopManifest = @{ python=(Join-Path $PSScriptRoot '.venv\Scripts\python.exe'); models=(Join-Path $PSScriptRoot 'models') } | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $desktopRelease 'runtime.json'),$desktopManifest,(New-Object System.Text.UTF8Encoding($false)))
Write-Host "Desktop application: $(Join-Path $desktopRelease 'LightningFlow.exe')"
