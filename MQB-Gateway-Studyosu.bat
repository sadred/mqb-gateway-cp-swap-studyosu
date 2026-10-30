@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "dist\MQB-Gateway-CP-SWaP-Studyosu.exe" (
    start "" "dist\MQB-Gateway-CP-SWaP-Studyosu.exe"
) else (
    python gateway_studio.py
)
