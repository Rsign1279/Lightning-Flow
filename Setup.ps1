param([string]$Model = 'tiny.en')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'Installing local Python dependencies and downloading the selected speech model. Audio and transcripts are never uploaded.'
if (Get-Command uv -ErrorAction SilentlyContinue) {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        uv venv --python 3.11 .venv
        if ($LASTEXITCODE) { throw 'Could not create Python environment' }
    }
    uv pip sync --python .venv\Scripts\python.exe requirements-lock.txt
} else {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE) { throw 'Install Python 3.11 or 3.12 x64 first' }
    }
    .venv\Scripts\python.exe -m pip install -r requirements-lock.txt
}
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
.venv\Scripts\python.exe -m lightningflow prepare --model $Model
if ($LASTEXITCODE) { throw 'Model installation failed' }
.venv\Scripts\python.exe -m lightningflow verify-model --model $Model
if ($LASTEXITCODE) { throw 'Model verification failed' }
Write-Host 'Ready. Open Start-LightningFlow.cmd; wait for READY, focus a text field and press Ctrl+Alt+F8.'
