Option Explicit
Dim files, shell, root, quote
Set files = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = files.GetParentFolderName(WScript.ScriptFullName)
quote = Chr(34)
shell.Run "powershell.exe -NoProfile -WindowStyle Hidden -File " & quote & root & "\Uninstall-LightningFlow.ps1" & quote, 0, False
