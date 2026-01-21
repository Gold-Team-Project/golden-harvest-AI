import os

from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
USE_LLM = False
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set")