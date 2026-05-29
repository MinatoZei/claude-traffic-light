@echo off
echo === Claude Code Traffic Light — Hook Setup ===
echo.
echo This copies the hook files into your project.
echo.
echo Usage:   setup_hooks.cmd  [project-path]
echo Example: setup_hooks.cmd  D:\my-project
echo          setup_hooks.cmd  .   ^(current directory^)
echo.

set "TARGET=%~1"
if "%TARGET%"=="" (
    set /p "TARGET=Project path (or Enter for current dir): "
)
if "%TARGET%"=="" set "TARGET=."
if not exist "%TARGET%" (
    echo ERROR: "%TARGET%" does not exist.
    pause
    exit /b 1
)

set "HOOKS_DIR=%TARGET%\.claude\hooks"
mkdir "%HOOKS_DIR%" 2>nul

copy /Y ".claude\settings.json" "%TARGET%\.claude\settings.json" >nul
copy /Y ".claude\hooks\traffic-update.cmd" "%HOOKS_DIR%\traffic-update.cmd" >nul

echo.
echo Done! Hook files copied to:
echo   %TARGET%\.claude\settings.json
echo   %HOOKS_DIR%\traffic-update.cmd
echo.
echo Now restart Claude Code in that project. The traffic light will work automatically.
echo (Make sure traffic_light.py is already running.)
pause
