Option Explicit
Dim shell, fso, folder, picked, sourceDb, destFolder, destDb, answer
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

folder = fso.GetParentFolderName(WScript.ScriptFullName)
Set picked = shell.BrowseForFolder(0, "Seleccione la carpeta de la versión anterior de GOLDENS PRO", 0, 0)
If picked Is Nothing Then WScript.Quit

sourceDb = picked.Self.Path & "\instance\goldens.db"
If Not fso.FileExists(sourceDb) Then
  MsgBox "No se encontró instance\goldens.db en esa carpeta.", 48, "Goldens Pro"
  WScript.Quit
End If

destFolder = folder & "\instance"
If Not fso.FolderExists(destFolder) Then fso.CreateFolder(destFolder)
destDb = destFolder & "\goldens.db"

answer = MsgBox("Esto copiará las citas y datos de la versión anterior. ¿Continuar?", 36, "Goldens Pro")
If answer <> 6 Then WScript.Quit

fso.CopyFile sourceDb, destDb, True
MsgBox "Datos copiados. Ahora abra GOLDENS PRO V9.", 64, "Goldens Pro"
