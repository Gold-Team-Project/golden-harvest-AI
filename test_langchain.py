# test_langchain.py
import os
from datetime import date
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 우리가 만든 모듈 임포트
from app.agents.intent_agent import parse_intent
from app.agents.wording_agent import generate_description
from app.document.schemas.documents import DocumentIntent, DocumentType


def test_intent():
    print("--- [1] 의도 파악 테스트 (Intent Parsing) ---")
    query = "내일 날짜로 삼성전자에 보낼 발주서 PDF 만들어줘"
    print(f"Q: {query}")

    # LangChain 실행
    result = parse_intent(query)

    print(f"A: {result}")
    print(f"   ㄴ Type: {result.document_type} (예상: PURCHASE_ORDER)")
    print(f"   ㄴ Format: {result.format} (예상: pdf)")
    # 날짜가 오늘이 아니라 '내일'로 찍히면 LLM이 작동한 것임
    print(f"   ㄴ Date: {result.start_date}")


def test_wording():
    print("\n--- [2] 멘트 생성 테스트 (Wording Generation) ---")
    intent = DocumentIntent(
        document_type=DocumentType.PURCHASE_ORDER,
        start_date=date.today(),
        end_date=date.today(),
        format="pdf"
    )

    # LangChain 실행
    msg = generate_description(intent)
    print(f"A: {msg}")


if __name__ == "__main__":
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ 에러: .env 파일에 GEMINI_API_KEY가 없습니다.")
    else:
        try:
            test_intent()
            test_wording()
            print("\n✅ 테스트 완료! 결과가 다채롭게 나오면 LangChain 작동 중입니다.")
        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
            print("API 키가 올바른지, 인터넷이 연결되었는지 확인해주세요.")