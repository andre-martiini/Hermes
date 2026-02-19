import os
from google import genai
from dotenv import load_dotenv

load_dotenv(dotenv_path='Hermes-Bot/.env')
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print(f"Testing key: {GEMINI_API_KEY[:4]}...{GEMINI_API_KEY[-4:]}")

client = genai.Client(api_key=GEMINI_API_KEY)

try:
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents='Hi'
    )
    print("Success:", response.text)
except Exception as e:
    print("Failure:", e)
