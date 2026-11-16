param([string]$Release = 'desktop-dist\LightningFlow')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$installerWork = Join-Path $PSScriptRoot '.work\installer-build'
New-Item -ItemType Directory -Path $installerWork -Force | Out-Null
$env:LIGHTNINGFLOW_RELEASE = Join-Path $PSScriptRoot $Release
$env:LIGHTNINGFLOW_PAYLOAD = Join-Path $installerWork 'desktop-payload.zip'
@'
import os,zipfile
from pathlib import Path
root=Path(os.environ['LIGHTNINGFLOW_RELEASE'])
payload=Path(os.environ['LIGHTNINGFLOW_PAYLOAD'])
with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED) as archive:
    for item in root.rglob('*'):
        if item.is_file() and item.name!='runtime.json' and not any(part in ('.runtime','models','__pycache__') for part in item.relative_to(root).parts):
            archive.write(item,item.relative_to(root))
print(payload)
'@ | .venv\Scripts\python.exe -
if ($LASTEXITCODE) { throw 'Could not create installer payload' }
.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name LightningFlow-Setup --icon (Join-Path $PSScriptRoot 'assets\lightningflow.ico') --version-file (Join-Path $PSScriptRoot 'assets\version-info.txt') --collect-data customtkinter --exclude-module numpy --add-data "$(Join-Path $installerWork 'desktop-payload.zip'):." --distpath (Join-Path $PSScriptRoot 'installers') --workpath $installerWork --specpath $installerWork installer_main.py
if ($LASTEXITCODE) { throw 'Installer executable build failed' }
