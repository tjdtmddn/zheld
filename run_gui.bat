@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_gui.ps1"
if errorlevel 1 (
    echo.
    echo GUI 실행에 실패했습니다. 위 오류 내용을 확인하세요.
    pause
)
endlocal
