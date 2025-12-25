@echo off
cd /d "%~dp0"
color 0A
echo ===============================================
echo   PASSO 1: VERIFICACAO (NAO FECHE A JANELA)
echo ===============================================
echo.
echo O script vai verificar se voce tem o Git instalado.
echo Pressione ENTER para continuar...
pause >nul

:: Verifica Git
where git >nul 2>nul
if %errorlevel% neq 0 (
    color 0C
    echo.
    echo [ERRO CRITICO] O GIT NAO ESTA INSTALADO! 🛑
    echo.
    echo O Windows nao encontrou o comando 'git'.
    echo Voce NAO instalou o Git ou precisa reiniciar o PC.
    echo.
    echo Baixe e instale: https://git-scm.com/download/win
    echo.
    echo Pressione ENTER para sair e instalar o Git...
    pause >nul
    exit
)

echo.
echo [OK] Git encontrado! Continuando...
echo.

echo ===============================================
echo      PREPARANDO ARQUIVOS (GIT INIT)
echo ===============================================

:: Configura identidade para evitar erro "Author identity unknown"
git config --global user.email "admin@neoproject.com"
git config --global user.name "Neo Admin"

git init
git add .
git commit -m "Upload Final Tool"
git branch -M main

:: Remove remote antigo
git remote remove origin 2>nul
:: Adiciona novo
git remote add origin https://github.com/Anonymoaps/neo-social-backend.git

echo.
echo [ATENCAO] TENTANDO ENVIAR AGORA...
echo Se pedir senha, faca o login na janela que abrir.
echo.
git push -u origin main

if %errorlevel% neq 0 (
    color 0C
    echo.
    echo [ERRO] FALHA NO ENVIO.
    echo Verifique sua internet ou se o GitHub esta bloqueado.
) else (
    echo.
    echo [SUCESSO] CODIGO ENVIADO PARA O GITHUB! 🚀
)

echo.
echo FIM DO PROCESSO.
echo Pressione ENTER para fechar...
pause >nul
