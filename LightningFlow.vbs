Option Explicit
Dim files, shell, root, exe, python, quote
Set files = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = files.GetParentFolderName(WScript.ScriptFullName)
quote = Chr(34)
shell.CurrentDirectory = root
exe = root & "\desktop-dist\LightningFlow\LightningFlow.exe"
python = root & "\.venv\Scripts\pythonw.exe"
If files.FileExists(exe) Then
    shell.Run quote & exe & quote, 1, False
ElseIf files.FileExists(python) Then
    shell.Run quote & python & quote & " " & quote & root & "\desktop_main.py" & quote, 0, False
Else
    MsgBox "Install LightningFlow with LightningFlow-Setup.exe, then open it from the Start menu.", 48, "LightningFlow"
End If
