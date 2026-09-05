Option Explicit
Dim shell, fso, folder, desktop, link
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

folder = fso.GetParentFolderName(WScript.ScriptFullName)
desktop = shell.SpecialFolders("Desktop")

Set link = shell.CreateShortcut(desktop & "\GOLDENS PRO.lnk")
link.TargetPath = "wscript.exe"
link.Arguments = """" & folder & "\INICIAR_GOLDENS.vbs"""
link.WorkingDirectory = folder
link.Description = "Abrir Goldens Pro"
link.Save

MsgBox "Acceso directo GOLDENS PRO creado en el escritorio.", 64, "Goldens Pro"
