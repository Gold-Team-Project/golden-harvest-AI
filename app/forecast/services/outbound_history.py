# app/services/forecast/outbound_history.py
import requests
from datetime import date
from typing import List, Dict, Optional
from app.config import JAVA_API_URL, JAVA_PAGE_SIZE, JAVA_MAX_PAGES


def fetch_outbounds_from_java(
    sku_no: str,
    start_date: date,
    end_date: date,
    lot_no: Optional[str] = None
) -> List[Dict]:

    all_rows: List[Dict] = []

    for page in range(1, JAVA_MAX_PAGES + 1):
        params = {
            "page": page,
            "size": JAVA_PAGE_SIZE,
            "skuNo": sku_no,
            "lotNo": lot_no,
            "startDate": str(start_date),
            "endDate": str(end_date),
        }

        url = f"{JAVA_API_URL}/api/outbound"
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()

        json_body = res.json()
        print("JAVA OUTBOUND RESPONSE:", json_body)

        rows = res.json().get("data", [])
        if not rows:
            break

        all_rows.extend(rows)

        if len(rows) < JAVA_PAGE_SIZE:
            break

    return all_rows
