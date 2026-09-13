@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
python server.py >> logs\server.log 2>&1
