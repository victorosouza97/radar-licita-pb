@echo off
chcp 65001 >nul
title Radar Licita PB
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python app.py
pause
