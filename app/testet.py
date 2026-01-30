import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("--- 사용 가능한 임베딩 모델 목록 ---")
for m in genai.list_models():
    if 'embedContent' in m.supported_generation_methods:
        print(f"모델명: {m.name}")