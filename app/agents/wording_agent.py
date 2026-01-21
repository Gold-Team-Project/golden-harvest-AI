# app/agents/wording_agent.py
from app.schemas.intent import DocumentIntent
from app.config import USE_LLM
from app.agents.gemini_client import generate_text

SYSTEM_PROMPT = """
너는 ERP 시스템의 문서 생성 결과를 설명하는 역할이다.
입력된 intent 정보를 바탕으로 사용자가 이해하기 쉽게 2~3문장으로 요약해라.
"""


def generate_description(intent: DocumentIntent):
    # 1. Fallback 메시지 정의 (실패 시 사용할 문구)
    fallback_msg = f"{intent.start_date}부터 {intent.end_date}까지의 입고 내역을 엑셀 파일로 정리했습니다."

    if not USE_LLM:
        return fallback_msg

    try:
        # 2. LLM 호출 (이미 client 내부에서 3번 재시도 로직이 돔)
        prompt = f"{SYSTEM_PROMPT}\n\n[Intent 정보]\n{intent}"
        return generate_text(prompt)

    except Exception as e:
        # 3. 3번 재시도 후에도 실패하면 여기서 잡힘 -> Fallback 반환
        print(f"⚠️ LLM 설명 생성 최종 실패: {e}")
        return fallback_msg