@echo off
cd /d "%~dp0"
echo ==========================================
echo      NEO AUTO-UPDATER (FORCE PUSH)
echo ==========================================
echo.

:: 1. Adicionar tudo
echo [1/3] Adicionando arquivos...
git add .

:: 2. Commit (Pede mensagem ou usa padrao)
set /p commit_msg="Digite a mensagem do commit (Enter para texto padrao): "
if "%commit_msg%"=="" set commit_msg="Atualizacao Automatica NEO v2"

echo [2/3] Commitando: "%commit_msg%"...
git commit -m "%commit_msg%"

:: 3. Push
echo [3/3] Enviando para o GitHub...
git push origin main

echo.
echo ==========================================
echo      SUCESSO! SITE ATUALIZADO.
echo ==========================================
pause
