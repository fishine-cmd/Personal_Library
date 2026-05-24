@echo off
REM Double-click to launch the Flask app AND MinerU service in two
REM independent terminal windows (neither blocks the other).
cd /d "%~dp0"

start "Library System" cmd /k start.bat
start "MinerU API" powershell -NoExit -ExecutionPolicy Bypass -File ".\mineru.ps1"

exit
