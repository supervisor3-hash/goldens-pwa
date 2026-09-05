Option Explicit
Dim shell, fso, folder, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)

cmd = "cmd /c cd /d """ & folder & """ && pythonw app.py"
shell.Run cmd, 0, False

WScript.Sleep 1800
shell.Run "http://127.0.0.1:5000", 1, False
