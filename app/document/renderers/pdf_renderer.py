import os
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle

FONT_NAME = 'Helvetica'
FONT_PATH = os.path.join(os.path.dirname(__file__), "../fonts/NanumGothic.ttf")

if os.path.exists(FONT_PATH):
    try:
        pdfmetrics.registerFont(TTFont('Nanum', FONT_PATH))
        FONT_NAME = 'Nanum'
    except Exception:
        pass

# 2. 디자인 컬러 팔레트 (모던한 네이비/그레이 톤)
COLOR_PRIMARY = colors.HexColor("#2C3E50")
COLOR_ACCENT = colors.HexColor("#34495E")
COLOR_GRAY_TEXT = colors.HexColor("#7F8C8D")
COLOR_LIGHT_BG = colors.HexColor("#ECF0F1")
COLOR_BORDER = colors.HexColor("#BDC3C7")


def generate_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4  # 595.27, 841.89


    c.setFont(FONT_NAME, 28)
    c.setFillColor(COLOR_PRIMARY)
    c.drawString(50, height - 60, data.get("doc_title", "문서"))

    c.setFont(FONT_NAME, 10)
    c.setFillColor(colors.black)

    info_x = width - 50
    info_y = height - 55

    def draw_header_info(label, value, y_pos):
        c.setFillColor(COLOR_GRAY_TEXT)
        c.drawRightString(info_x - 100, y_pos, label)  # 라벨
        c.setFillColor(colors.black)
        c.drawRightString(info_x, y_pos, value)  # 값

    draw_header_info("발주번호 :", data.get('doc_no', '-'), info_y)
    draw_header_info("발주일자 :", data.get('doc_date', '-'), info_y - 15)
    draw_header_info("납품요청일 :", data.get('due_date', '-'), info_y - 30)

    c.setStrokeColor(COLOR_PRIMARY)
    c.setLineWidth(2)
    c.line(50, height - 90, width - 50, height - 90)

    section_y = height - 130

    def draw_party_info(x_start, title, info):
        c.setFont(FONT_NAME, 12)
        c.setFillColor(COLOR_ACCENT)
        c.drawString(x_start, section_y, title)

        c.setFont(FONT_NAME, 10)
        c.setFillColor(colors.black)
        start_text_y = section_y - 25
        line_height = 16

        c.setFont(FONT_NAME, 11)
        c.drawString(x_start, start_text_y, info.get('name', ''))

        c.setFont(FONT_NAME, 9)
        c.setFillColor(colors.darkgray)
        c.drawString(x_start, start_text_y - line_height, f"담당자: {info.get('contact', '-')}")
        c.drawString(x_start, start_text_y - line_height * 2, f"Tel: {info.get('tel', '-')}")
        if 'addr' in info:
            c.drawString(x_start, start_text_y - line_height * 3, f"주소: {info.get('addr', '')}")

    buyer_label = data.get("buyer", {}).get("label", "발주처 (To)")
    draw_party_info(50, buyer_label, data.get("buyer", {}))

    supplier_label = data.get("supplier", {}).get("label", "공급처 (From)")
    draw_party_info(300, supplier_label, data.get("supplier", {}))

    table_headers = ['품목명', '산지', '규격', '단위', '수량', '금액']
    table_data = [table_headers] + data.get("table_items", [])

    items_count = len(data.get("table_items", []))
    total_amt = data.get("total_amount", 0)

    t = Table(table_data, colWidths=[140, 60, 80, 50, 60, 100])

    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_ACCENT),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

        # (2) 데이터 로우 스타일
        ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),

        ('LINEBELOW', (0, 0), (-1, -1), 0.5, COLOR_BORDER),

        ('ALIGN', (0, 1), (3, -1), 'CENTER'),
        ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
    ]))

    w, h = t.wrapOn(c, width, height)
    table_y = height - 250 - h
    t.drawOn(c, 50, table_y)

    footer_y = table_y - 40

    # 합계 라벨
    c.setFont(FONT_NAME, 12)
    c.setFillColor(COLOR_GRAY_TEXT)
    c.drawRightString(width - 160, footer_y, "Total Amount :")

    c.setFont(FONT_NAME, 16)
    c.setFillColor(COLOR_PRIMARY)  # 빨간색 대신 메인 컬러 사용 (더 전문적임)
    c.drawRightString(width - 50, footer_y, f"₩ {total_amt:,}")

    c.setStrokeColor(COLOR_BORDER)
    c.setLineWidth(1)
    c.line(width - 250, footer_y - 15, width - 50, footer_y - 15)

    c.setFont(FONT_NAME, 10)
    c.setFillColor(colors.black)
    c.drawRightString(width - 50, footer_y - 40, "2025년 12월 31일")
    c.drawRightString(width - 50, footer_y - 60, f"{data.get('buyer', {}).get('name', '')}   (인)")
    c.setFont(FONT_NAME, 8)
    c.setFillColor(colors.gray)
    c.drawString(50, 40, "* 본 문서는 전산으로 발급되었으며, 별도의 직인 없이 유효합니다.")
    c.drawString(50, 25, "* 문의사항은 담당자에게 연락 바랍니다.")

    c.drawRightString(width - 50, 25, "Page 1 of 1")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()