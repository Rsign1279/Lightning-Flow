param([string]$AppRoot = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $AppRoot
$runtimePython = Join-Path $AppRoot '.runtime\Scripts\python.exe'
if (Get-Command uv -ErrorAction SilentlyContinue) {
    if (-not (Test-Path -LiteralPath $runtimePython)) {
        uv venv --python 3.11 (Join-Path $AppRoot '.runtime')
        if ($LASTEXITCODE) { throw 'Could not create the GPU runtime. Install Python 3.11 x64.' }
    }
    uv pip sync --python $runtimePython (Join-Path $AppRoot 'runtime-requirements.txt')
} else {
    if (-not (Test-Path -LiteralPath $runtimePython)) {
        python -m venv (Join-Path $AppRoot '.runtime')
        if ($LASTEXITCODE) { throw 'Install Python 3.11 or 3.12 x64 first.' }
    }
    & $runtimePython -m pip install -r (Join-Path $AppRoot 'runtime-requirements.txt')
}
if ($LASTEXITCODE) { throw 'GPU dependency installation failed.' }
New-Item -ItemType Directory -Path (Join-Path $AppRoot 'models') -Force | Out-Null
@{ python=$runtimePython; models=(Join-Path $AppRoot 'models') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $AppRoot 'runtime.json') -Encoding utf8
Write-Host 'GPU runtime installed. Open LightningFlow and choose a speech model.'
