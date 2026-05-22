"""Bóc tách kết quả tra cứu MST từ HTML trả về.

Cấu trúc bảng kết quả thực tế (table.ta_border):
    STT | MST | Tên người nộp thuế | Cơ quan thuế quản lý | Trạng thái MST
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from bs4 import BeautifulSoup

from src.config import CAPTCHA_ERROR_KEYWORDS, NOT_FOUND_KEYWORDS, SEL_RESULT_TABLE


@dataclass
class LookupResult:
    status: str
    rows: List[dict] = field(default_factory=list)
    raw_message: Optional[str] = None


def _norm(text: str) -> str:
    return " ".join(text.split()).strip().lower()


_HEADER_MAP = {
    "stt": "stt",
    "mst": "mst",
    "mã số thuế": "mst",
    "tên người nộp thuế": "ten_nnt",
    "cơ quan thuế quản lý": "co_quan_thue",
    "trạng thái mst": "trang_thai",
    "trạng thái": "trang_thai",
}


def _map_header(h: str) -> str:
    h = _norm(h)
    if h in _HEADER_MAP:
        return _HEADER_MAP[h]
    for key, val in _HEADER_MAP.items():
        if key in h:
            return val
    return h.replace(" ", "_") or "col"


def parse(html: str) -> LookupResult:
    """Phân tích HTML sau khi submit form tra cứu.

    Returns:
        LookupResult với status:
        - SUCCESS: tìm thấy bảng kết quả với ít nhất 1 dòng
        - NOT_FOUND: trang báo không có dữ liệu
        - CAPTCHA_WRONG: trang báo captcha sai
        - UNKNOWN: không khớp pattern nào
    """
    soup = BeautifulSoup(html, "lxml")

    # Bảng kết quả nằm trong table.ta_border → check trước, vì đáng tin cậy nhất
    table = soup.select_one(SEL_RESULT_TABLE)
    if table is not None:
        rows = _parse_table(table)
        if rows:
            return LookupResult(status="SUCCESS", rows=rows)

    body_text = _norm(soup.get_text(" "))

    for kw in CAPTCHA_ERROR_KEYWORDS:
        if kw in body_text:
            return LookupResult(status="CAPTCHA_WRONG", raw_message=kw)

    for kw in NOT_FOUND_KEYWORDS:
        if kw in body_text:
            return LookupResult(status="NOT_FOUND", raw_message=kw)

    return LookupResult(status="UNKNOWN", raw_message=body_text[:200])


def _parse_table(table) -> List[dict]:
    all_trs = table.find_all("tr")
    if not all_trs:
        return []

    # Header row: ưu tiên row có <th>, fallback row đầu
    header_row = next((tr for tr in all_trs if tr.find("th")), all_trs[0])
    header_cells = header_row.find_all(["th", "td"])
    keys = [_map_header(c.get_text()) for c in header_cells]

    rows: List[dict] = []
    for tr in all_trs:
        if tr is header_row:
            continue
        if tr.find("th"):  # bỏ qua các header row khác (defensive)
            continue
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        row = {}
        for i, td in enumerate(tds):
            key = keys[i] if i < len(keys) else f"col_{i}"
            row[key] = " ".join(td.get_text(" ", strip=True).split())
        if any(row.values()):
            rows.append(row)
    return rows
