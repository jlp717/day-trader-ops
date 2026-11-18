@echo off
chcp 65001 >nul
cd /d "%~dp0"
python trader-ops\run\panel.py %*
pause
