@echo off
rem Remove hooks and autostart, and stop the island. Does not touch Claude Code.
cd /d "%~dp0"
python setup.py uninstall
echo.
pause
