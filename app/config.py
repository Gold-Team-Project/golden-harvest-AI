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
WEATHER_LAT = float(os.getenv("WEATHER_LAT"))
WEATHER_LON = float(os.getenv("WEATHER_LON"))
WEATHER_TIMEZONE = os.getenv("WEATHER_TIMEZONE")

DB_CONNECTION = os.getenv("DATABASE_URL")
# 페이징

# 임베딩
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=GEMINI_API_KEY
)
MDB_HOST = os.getenv("MDB_HOST")
MDB_PORT = int(os.getenv("MDB_PORT"))
MDB_DBNAME = os.getenv("MDB_DBNAME")
MDB_USER = os.getenv("MDB_USER")
MDB_PASSWORD = os.getenv("MDB_PASSWORD")