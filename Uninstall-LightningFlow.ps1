$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$uninstallRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$uninstallExpected = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\LightningFlow'))
if ($uninstallRoot -ne $uninstallExpected) { throw 'Automatic uninstall is restricted to the standard per-user installation. Remove a custom portable folder manually.' }
if ([System.Windows.Forms.MessageBox]::Show('Uninstall LightningFlow? Saved settings and transcript history will be kept. Close LightningFlow before continuing.','Uninstall LightningFlow','YesNo','Question') -ne 'Yes') { exit }
$uninstallRunning = Get-Process -Name LightningFlow -ErrorAction SilentlyContinue | Where-Object { $_.Path -and [System.IO.Path]::GetFullPath($_.Path) -eq (Join-Path $uninstallRoot 'LightningFlow.exe') }
if ($uninstallRunning) {
    [System.Windows.Forms.MessageBox]::Show('Quit LightningFlow from its tray icon, then uninstall again.','LightningFlow is running','OK','Information') | Out-Null
    exit 1
}
foreach ($shortcutPath in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'LightningFlow.lnk'), (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\LightningFlow.lnk'))) {
    if (Test-Path -LiteralPath $shortcutPath) { Remove-Item -LiteralPath $shortcutPath -Force }
}
Remove-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name LightningFlowDesktop -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\LightningFlowDesktop') {
    Remove-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\LightningFlowDesktop' -Recurse -Force
}
# Exact resolved target was checked above; no home/profile tree is removed.
Set-Location -LiteralPath $env:TEMP
Remove-Item -LiteralPath $uninstallRoot -Recurse -Force
[System.Windows.Forms.MessageBox]::Show('LightningFlow was removed. Saved data remains under LocalAppData\LightningFlow.','LightningFlow','OK','Information') | Out-Null
