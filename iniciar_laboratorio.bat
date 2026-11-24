@echo off
title Laboratorio Copy Trade
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo Iniciando o laboratorio... o painel abre no navegador em http://127.0.0.1:8765
echo Para parar, feche esta janela ou aperte Ctrl+C.
py -m lab
pause
