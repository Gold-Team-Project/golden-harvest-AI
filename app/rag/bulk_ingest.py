import os
import glob
from app.rag.ingest import ingest_pdf_report

# 1. 파일명 분석용 사전 (있으면 쓰고, 없으면 맙니다)
CATEGORY_MAP = {
    "apple": "사과",
    "cabbage": "배추",
    "radish": "무",
    "onion": "양파",
    "garlic": "마늘",
    "pepper": "건고추"
}

# 2. 기본 설정값 (파일명 분석 실패 시 사용할 값)
DEFAULT_CATEGORY = "농업관측"
DEFAULT_DATE = "2025-08"


def process_all_files(data_folder="data"):
    """
    data 폴더의 모든 PDF를 무조건 DB에 넣습니다.
    파일명 규칙이 안 맞으면 기본값으로 넣습니다.
    """
    pdf_files = glob.glob(os.path.join(data_folder, "*.pdf"))

    print(f"📂 총 {len(pdf_files)}개의 PDF 파일을 찾았습니다.\n")

    success_count = 0
    fail_count = 0

    for file_path in pdf_files:
        try:
            filename = os.path.basename(file_path)

            # --- [유연한 메타데이터 추출 로직] ---
            # 우선 기본값으로 설정해둡니다.
            category = DEFAULT_CATEGORY
            report_date = DEFAULT_DATE

            # 파일명에 '_'가 2개 이상 있으면 규칙을 시도해봅니다. (예: 2025_08_apple.pdf)
            name_parts = filename.split("_")
            if len(name_parts) >= 3:
                year = name_parts[0]
                month = name_parts[1]
                eng_category = name_parts[2].replace(".pdf", "")  # .pdf 제거

                # 추출 성공 시 덮어쓰기
                report_date = f"{year}-{month}"
                category = CATEGORY_MAP.get(eng_category, eng_category)  # 매핑 없으면 영어 그대로 사용
                print(f"   👉 [규칙 감지] {filename} -> {category} / {report_date}")
            else:
                # 규칙이 안 맞으면 그냥 기본값 사용
                print(f"   👉 [일반 파일] {filename} -> {category} (기본값 적용)")

            # -----------------------------------

            # 기존 함수 호출하여 적재
            ingest_pdf_report(file_path, category=category, report_date=report_date)
            success_count += 1

        except Exception as e:
            fail_count += 1
            continue



if __name__ == "__main__":
    process_all_files()