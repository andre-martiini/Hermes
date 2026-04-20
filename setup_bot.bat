
@echo off
setlocal
echo Configurando ambiente para o Hermes Bot...
if not exist venv (
  python -m venv venv
)
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Instalando runtime local de precisao para PDFs...
python skills\hermes-pdf-inspector\scripts\install_pdf_inspector.py
if errorlevel 1 (
  echo Falha ao instalar o pdf-inspector local.
  exit /b 1
)
echo.
echo Tudo pronto! O bot agora pode usar:
echo venv\Scripts\python hermes_cli.py [comando]
pause
