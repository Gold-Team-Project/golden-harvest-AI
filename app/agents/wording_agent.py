from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.config import llm, USE_LLM
from app.schemas.documents import DocumentIntent


def generate_description(intent: DocumentIntent) -> str:
    fallback_msg = f"{intent.start_date}~{intent.end_date} {intent.document_type.value} 문서를 생성했습니다."

    if not USE_LLM:
        return fallback_msg

    try:
        prompt = ChatPromptTemplate.from_template(
            "너는 ERP 시스템 봇이다. 다음 의도(Intent)를 바탕으로 사용자에게 문서 생성 완료 메시지를 2문장 이내로 정중하게 작성해라.\n\n[의도]\n{intent}"
        )

        chain = prompt | llm | StrOutputParser()
        return chain.invoke({"intent": str(intent)})

    except Exception as e:
        print(f"⚠️ Wording Error: {e}")
        return fallback_msg