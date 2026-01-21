# app/agents/gemini_client.py
from google import genai
from google.api_core.exceptions import ResourceExhausted
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from app.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)


# 🔍 [핵심] 429 에러인지 판단하는 커스텀 함수
def is_quota_error(exception):
    """
    발생한 에러가 429(Quota/Resource Exhausted)인지 확인합니다.
    google-genai SDK가 버전에 따라 던지는 에러 타입이 다를 수 있어,
    에러 메시지 내용을 직접 검사하는 것이 가장 확실합니다.
    """
    # 1. 명확한 ResourceExhausted 타입인 경우
    if isinstance(exception, ResourceExhausted):
        return True

    # 2. 에러 메시지(String) 안에 429나 RESOURCE_EXHAUSTED가 포함된 경우 (현재 겪고 계신 상황)
    error_msg = str(exception)
    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
        return True

    return False


# 🚀 재시도 설정: 커스텀 필터 적용 + 횟수 증가
@retry(
    retry=retry_if_exception(is_quota_error),  # 위 함수가 True일 때만 재시도
    wait=wait_exponential(multiplier=1, min=2, max=15),  # 대기 시간 늘림 (2초~15초)
    stop=stop_after_attempt(6),  # 횟수 늘림 (3회 -> 6회, 429는 해소에 시간이 좀 걸림)
    reraise=True
)
def generate_text(prompt: str) -> str:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text