@echo off
title Laboratorio Copy Trade
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo.
    echo  Python nao encontrado neste computador.
    echo  Instale o Python 3.10 ou mais novo em https://www.python.org/downloads/
    echo  e marque a opcao "Add python.exe to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

echo Iniciando o laboratorio... o painel abre no navegador em http://127.0.0.1:8765
echo Para parar, feche esta janela ou aperte Ctrl+C.
echo.
%PY% -m lab
echo.
echo O laboratorio parou. Se apareceu um erro acima, tire um print dele.
pause
