Option Explicit
Dim filesystem, script, arguments, shell, environment, powershell
Set filesystem=CreateObject("Scripting.FileSystemObject")
Set environment=CreateObject("WScript.Shell")
powershell=environment.ExpandEnvironmentStrings("%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
script=filesystem.BuildPath(filesystem.GetParentFolderName(WScript.ScriptFullName),"Export-TdrDump.ps1")
arguments="-NoProfile -NonInteractive -ExecutionPolicy Bypass -File " & Chr(34) & script & Chr(34)
Set shell=CreateObject("Shell.Application")
On Error Resume Next
shell.ShellExecute powershell,arguments,"","runas",0
If Err.Number <> 0 Then
    MsgBox "The private kernel-report export was not started. Administrator approval is required; no driver or Windows permission settings were changed.",48,"LightningFlow diagnostics"
    WScript.Quit 1
End If
