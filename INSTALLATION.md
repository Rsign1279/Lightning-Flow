# Installation and builds

## Requirements

- Windows 11 x64 and a compatible NVIDIA driver/GPU. RTX 5070 CUDA inference was exercised; other GPUs require validation.
- Python 3.11 or 3.12 x64, or uv capable of installing Python 3.11.
- Network for initial dependencies and explicitly selected model downloads. No network is required for installed-model dictation.

## Desktop installer

Get `LightningFlow-Setup.exe` from this project's GitHub Releases when published. Current binaries are unsigned. The installer prepares a per-user desktop app, Start menu/Desktop shortcuts, uninstaller and GPU runtime. No large speech model is embedded. Onboarding offers model downloads; selecting one is explicit consent. Reopen from the normal shortcut; no terminal is needed for daily use.

Windows can show warnings for unsigned software. This project does not instruct users to disable Windows security. Source builds are available for inspection. Trusted code signing requires a maintainer-controlled certificate; no certificate/private key is included.

## Source build

From the cloned repository root in PowerShell:

```powershell
.\Setup.ps1 -Model tiny.en
.\.venv\Scripts\python.exe -m pytest -q
.\Build.ps1
.\Build-Desktop.ps1
.\Build-Installer.ps1
```

Outputs: Python wheel under `dist`, desktop under `desktop-dist\LightningFlow`, installer under `installers`. Temporary build products stay under `.work`. The installer prepares its own `.runtime`; development uses `.venv`. Models are managed separately and excluded from Git. `Setup-Runtime.ps1` repairs a packaged runtime; the desktop exposes a repair action.

The release workflow builds Windows installers from a version tag and publishes checksums. Release checks in the app are off by default. Updates are installed explicitly from Releases; no downloaded installer executes automatically.

## Controls

Select Ctrl+Win and Hold + double press in Settings → Shortcuts. Hold for normal dictation, release either modifier group to stop capture, double-tap for hands-free recording and tap again to finish. Prefer Ctrl first. Do not run a competing dictation utility on the same chord. Ctrl+Alt+Escape cancels; Ctrl+Alt+F9 retries at the current cursor. Check the target before retrying an uncertain paste.

## Existing data

Preferences and opted-in history migrate to Windows-user DPAPI protection on save/open. Explicit exports and pre-existing backups are not retroactively encrypted or deleted. Back up wanted text through an explicit export before moving to another Windows account or reinstalling Windows; copying encrypted settings alone is not a portable backup. Uninstall keeps user data unless explicitly removed through the app.
