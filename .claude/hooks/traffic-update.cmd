@echo off
REM Write Claude Code status to traffic light status file
echo {"status":"%~1"} > "%USERPROFILE%\.claude\traffic_status.json"
