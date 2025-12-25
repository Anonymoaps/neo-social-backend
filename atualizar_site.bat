@echo off
cd /d "%~dp0"
title ATUALIZANDO NEO APP
color 0e

echo.
echo ==========================================
echo        ATUALIZADOR AUTOMATICO (V2)
echo ==========================================
echo.
echo 1. Adicionando mudancas...
git add .
echo.

set /p msg="Escreva o que mudou (ou so aperte ENTER): "
if "%msg%"=="" set msg="Atualizacao Automatica"

echo.
echo 2. Salvando: "%msg%"...
git commit -m "%msg%"
echo.

echo 3. Enviando para nuvem...
git push origin main

if %errorlevel% neq 0 (
    color 0c
    echo.
    echo [ERRO] O envio falhou.
    echo Verifique sua internet ou se o GitHub esta fora.
) else (
    color 0a
    echo.
    echo [SUCESSO] Site atualizado! O Render vai aplicar em 2min.
)

echo.
echo Pressione ENTER para sair...
pause >nul
