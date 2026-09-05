@echo off
setlocal
set "SCRIPT=%~dp0ABRIR_GOLDENS_V9.bat"
set "DESKTOP=%USERPROFILE%\Desktop"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$s=(New-Object -COM WScript.Shell).CreateShortcut('%DESKTOP%\GOLDENS PRO V9.lnk');" ^
 "$s.TargetPath='%SCRIPT%';" ^
 "$s.WorkingDirectory='%~dp0';" ^
 "$s.Description='Goldens Pro V9';" ^
 "$s.Save()"
echo.
echo Acceso directo GOLDENS PRO V9 creado en el escritorio.
pause
