$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
.venv\Scripts\python.exe -m compileall -q lightningflow
if ($LASTEXITCODE) { throw 'Compilation failed' }
.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE) { throw 'Tests failed' }
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv build --wheel --out-dir dist
} else {
    .venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir dist
}
if ($LASTEXITCODE) { throw 'Wheel build failed' }
