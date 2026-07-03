@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "" pythonw neon_studio_desktop.py
