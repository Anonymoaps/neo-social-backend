@echo off
echo ==========================================
echo    INICIANDO NEO PROJECT (V2)
echo ==========================================
echo.
echo 1. Abrindo o Site no Navegador...
start http://localhost:8000

echo.
echo 2. Iniciando Servidor Backend...
echo.
cd /d "%~dp0"
python -m uvicorn main:app --reload

pause
