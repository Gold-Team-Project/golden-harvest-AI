# app/agents/intent_agent.py
from datetime import date
from app.schemas.intent import DocumentIntent
from app.schemas.documents import DocumentType
from app.config import USE_LLM
from app.agents.gemini_client import generate_text
import json


def parse_intent(user_message: str) -> DocumentIntent:
    # 🔒 기본 Mock (fallback)
    fallback_intent = DocumentIntent(
        document_type=DocumentType.INBOUND,
        start_date=date(2026, 1, 10),
        end_date=date(2026, 1, 17),
        format="excel"
    )

    if not USE_LLM:
        return fallback_intent

    try:
        prompt = f"""
너는 ERP 문서 요청을 분석하는 역할이다.
반드시 JSON만 반환해라. 마크다운 코드 블록(```json) 없이 순수 JSON 텍스트만 출력해.

형식:
{{
  "document_type": "INBOUND",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "format": "excel"
}}

사용자 요청:
{user_message}
"""
        # Client에서 3회 재시도 후 결과 반환
        text = generate_text(prompt)

        # JSON 파싱 (마크다운 방어 로직 추가)
        clean_text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)

        return DocumentIntent(
            document_type=DocumentType[data["document_type"]],
            start_date=date.fromisoformat(data["start_date"]),
            end_date=date.fromisoformat(data["end_date"]),
            format=data.get("format", "excel")
        )

    except Exception as e:
        # Client에서 429로 3번 실패했거나, JSON 파싱이 터진 경우 모두 여기서 처리
        print("⚠️ LLM 실패 → fallback 사용:", e)
        return fallback_intent