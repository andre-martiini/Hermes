
@echo off
echo Configurando ambiente para o Hermes Bot...
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
echo.
echo Tudo pronto! O bot agora pode usar:
echo venv\Scripts\python hermes_cli.py [comando]
pause
