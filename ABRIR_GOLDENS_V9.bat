@echo off
setlocal
cd /d "%~dp0"

title Goldens Pro V9

echo.
echo ==========================================
echo       INICIANDO GOLDENS PRO V9
echo ==========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no fue encontrado.
    echo.
    echo Instale Python o revise la instalacion.
    pause
    exit /b 1
)

echo Cerrando una version anterior si existe...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

timeout /t 1 /nobreak >nul

if exist goldens_inicio.log del /q goldens_inicio.log >nul 2>&1

echo Iniciando servidor...
start "" /min cmd /c "cd /d ""%~dp0"" && python app.py > goldens_inicio.log 2>&1"

echo Esperando que Goldens este listo...
set READY=0

for /L %%i in (1,1,20) do (
    timeout /t 1 /nobreak >nul
    curl -s --max-time 1 http://127.0.0.1:5000/health >nul 2>&1
    if not errorlevel 1 (
        set READY=1
        goto :ready
    )
)

:ready
if "%READY%"=="1" (
    echo.
    echo GOLDENS PRO ESTA LISTO.
    start "" http://127.0.0.1:5000
    timeout /t 2 /nobreak >nul
    exit
)

echo.
echo NO SE PUDO INICIAR GOLDENS.
echo Se abrira el error automaticamente.
echo.
start "" notepad.exe "%~dp0goldens_inicio.log"
pause
exit /b 1
