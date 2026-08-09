@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
set GOOGLE_APPLICATION_CREDENTIALS=%~dp0..\..\firebase_service_account_key.json
set FIREBASE_STORAGE_BUCKET=gestao-hermes.firebasestorage.app
node index.js >> logs\worker.log 2>&1
