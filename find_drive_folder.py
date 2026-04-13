import os
import sys
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_service():
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        return build('drive', 'v3', credentials=creds)
    return None

service = get_service()
if service:
    query = "name = 'Second Brain' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields='files(id, name)').execute()
    folders = results.get('files', [])
    for f in folders:
        print(f"ID: {f['id']} | Nome: {f['name']}")
else:
    print("Erro: token.json não encontrado.")
