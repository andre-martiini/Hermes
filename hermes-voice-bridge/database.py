import os
from functools import lru_cache

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore

load_dotenv()


@lru_cache(maxsize=1)
def get_db():
    project_id = os.getenv("FIREBASE_PROJECT_ID") or None
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    options = {"projectId": project_id} if project_id else None

    if not firebase_admin._apps:
        if credentials_path:
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred, options)
        else:
            firebase_admin.initialize_app(options=options)

    return firestore.client()
