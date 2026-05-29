import requests

url = "https://firebasestorage.googleapis.com/v0/b/gestao-hermes-slides-us-central1/o/imagens_geradas%2Fimg_848c4789.jpg?alt=media&token=ff4445ce-bd26-4b37-aa77-9ef133931e32"

try:
    r = requests.get(url, timeout=10)
    print(f"Status Code: {r.status_code}")
    print(f"Headers: {dict(r.headers)}")
    print(f"Response (first 300 chars): {r.text[:300]}")
except Exception as e:
    print(f"Error: {e}")
