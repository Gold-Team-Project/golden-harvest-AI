import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
USE_LLM = os.getenv("USE_LLM", "True").lower() == "true"

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing.")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0,
    google_api_key=GEMINI_API_KEY,
    max_retries=3
)


#Forecast
FORECAST_DEFAULT_HORIZON_MONTHS = int(os.getenv("FORECAST_DEFAULT_HORIZON_MONTHS", "6"))

# Open-Meteo (no key) 기본 위치: 서울
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "37.5665"))
WEATHER_LON = float(os.getenv("WEATHER_LON", "126.9780"))
WEATHER_TIMEZONE = os.getenv("WEATHER_TIMEZONE", "Asia/Seoul")

# Java url
JAVA_API_URL = os.getenv("JAVA_API_URL", "http://localhost:8088")
DB_CONNECTION = os.getenv("DATABASE_URL")
# 페이징
JAVA_PAGE_SIZE = int(os.getenv("JAVA_PAGE_SIZE", "50"))
JAVA_MAX_PAGES = int(os.getenv("JAVA_MAX_PAGES", "50"))
# Naver
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

# 임베딩
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=GEMINI_API_KEY
)