from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_postgres import PGVector
from app.config import embeddings, DB_CONNECTION
import os

def ingest_pdf_report(file_path: str, category: str, report_date: str):
    """
    PDF 보고서를 벡터 DB에 저장하는 함수

    Args:
        file_path (str): PDF 파일 경로
        category (str): 품목명 (예: 사과, 배추)
        report_date (str): 발행년월 (예: 2025-08)
    """
    print(f"[처리 시작] {file_path} (품목: {category}, 날짜: {report_date})")

    # PDF 로드
    loader = PyPDFLoader(file_path)
    raw_documents = loader.load()
    print(f"   - PDF 페이지 수: {len(raw_documents)}장")

    # 텍스트 분할 (Chunking)
    # 문맥이 끊기지 않도록 1000자 단위로 자르고 200자는 앞뒤로 겹치게 함
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    splits = text_splitter.split_documents(raw_documents)
    print(f"   - 분할된 청크 수: {len(splits)}개")

    # 메타데이터 주입 (중요!)
    # 나중에 "사과"만 찾거나 "2025년 8월" 자료만 찾기 위해 태그를 답니다.
    for doc in splits:
        doc.metadata["category"] = category  # 품목
        doc.metadata["period"] = report_date  # 기간
        doc.metadata["source"] = "KREI_관측월보"

    # PGVector 저장
    PGVector.from_documents(
        embedding=embeddings,
        documents=splits,
        collection_name="agri_reports",
        connection=DB_CONNECTION,
        use_jsonb=True,
    )
    print("성공\n")


if __name__ == "__main__":
    sample_pdf = "data/2025_08_apple_report.pdf"

    if os.path.exists(sample_pdf):
        ingest_pdf_report(sample_pdf, category="사과", report_date="2025-08")
    else:
        print(f"❌ 파일을 찾을 수 없습니다: {sample_pdf}")
        print("테스트를 위해 data 폴더에 PDF를 넣거나 경로를 수정해주세요.")