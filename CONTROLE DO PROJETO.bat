@echo off
title Loot de Ofertas - Controle
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0controle-projeto.ps1" menu
echo.
pause
