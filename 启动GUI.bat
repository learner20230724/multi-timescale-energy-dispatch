@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -c "from energy_dispatch.gui import launch_gui; launch_gui()"
pause
