@echo off
setlocal
cd /d "%~dp0"
title Mapeador - execucao continua
echo ==========================================
echo Mapeador - execucao continua
echo Para parar de vez, feche esta janela.
echo A automacao de pesquisas pode ser ligada/desligada no navegador.
echo ==========================================
:loop
echo.
echo Verificando atualizacoes do GitHub...
git pull --ff-only
if errorlevel 1 (
  echo Nao foi possivel atualizar automaticamente. Vou iniciar a versao local.
)
echo.
echo Iniciando Mapeador...
py web_app.py
echo.
echo O Mapeador foi encerrado. Tentando reiniciar em 10 segundos...
timeout /t 10 /nobreak >nul
goto loop
