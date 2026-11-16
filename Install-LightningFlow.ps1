param([string]$Destination = (Join-Path $env:LOCALAPPDATA 'Programs\LightningFlow'), [switch]$PrepareRuntime, [string]$ExistingModels = '', [switch]$NoShortcuts, [switch]$NoRegister)
$ErrorActionPreference = 'Stop'
$installSource = [System.IO.Path]::GetFullPath($PSScriptRoot)
$installTarget = [System.IO.Path]::GetFullPath($Destination)
if (-not (Test-Path -LiteralPath (Join-Path $installSource 'LightningFlow.exe'))) { throw 'Run the installer from the built desktop application folder.' }
New-Item -ItemType Directory -Path $installTarget -Force | Out-Null
if ($installSource -ne $installTarget) {
    Get-ChildItem -LiteralPath $installSource -Force | Where-Object { $_.Name -notin @('.runtime','models') } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $installTarget -Recurse -Force
    }
}
if ($PrepareRuntime) { & (Join-Path $installTarget 'Setup-Runtime.ps1') -AppRoot $installTarget }
if ($ExistingModels -and (Test-Path -LiteralPath $ExistingModels)) {
    New-Item -ItemType Directory -Path (Join-Path $installTarget 'models') -Force | Out-Null
    foreach ($installModel in @('tiny.en','base.en','small.en')) {
        $installModelSource = Join-Path $ExistingModels $installModel
        if (Test-Path -LiteralPath (Join-Path $installModelSource 'sha256.json')) {
            Copy-Item -LiteralPath $installModelSource -Destination (Join-Path $installTarget 'models') -Recurse -Force
        }
    }
}
if (-not $NoShortcuts) {
    $shortcutShell = New-Object -ComObject WScript.Shell
    foreach ($shortcutPath in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'LightningFlow.lnk'), (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\LightningFlow.lnk'))) {
        $shortcut = $shortcutShell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $installTarget 'LightningFlow.exe'
        $shortcut.WorkingDirectory = $installTarget
        $shortcut.IconLocation = Join-Path $installTarget 'assets\lightningflow.ico'
        $shortcut.Save()
    }
}
if (-not $NoRegister) {
    $uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\LightningFlowDesktop'
    New-Item -Path $uninstallKey -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayName -Value 'LightningFlow' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayVersion -Value '0.5.0' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name InstallLocation -Value $installTarget -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayIcon -Value (Join-Path $installTarget 'LightningFlow.exe') -PropertyType String -Force | Out-Null
    $uninstallCommand = 'wscript.exe "' + (Join-Path $installTarget 'Uninstall-LightningFlow.vbs') + '"'
    New-ItemProperty -Path $uninstallKey -Name UninstallString -Value $uninstallCommand -PropertyType String -Force | Out-Null
}
Write-Host "Installed LightningFlow in $installTarget"
