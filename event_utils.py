# -*- coding: utf-8 -*-
"""이벤트 키·사전 명단 파싱 (카페 URL, evt-..., YYYYMMDD+일련 등)."""
import os
import re
import unicodedata
from datetime import datetime
from typing import Dict, Optional

# 레거시: YYMMDD + 3자리 일련 (예: 260405-001)
EVENT_CODE_PATTERN = re.compile(r"^\d{6}-\d{3}$")
# 신규: YYYYMMDD + 2자리 일련 (예: 2026040501)
EVENT_ID_DATE_SERIAL_PATTERN = re.compile(r"^\d{8}\d{2}$")

_WEEKDAYS_KO = "월화수목금토일"


def format_event_at_display(iso_str: Optional[str]) -> str:
    """헤더 등에 쓰는 짧은 한국어 일시 (예: 4월 5일 (일) 15:00)."""
    if not iso_str or not str(iso_str).strip():
        return ""
    s = str(iso_str).strip().replace("Z", "+00:00")
    try:
        if "T" in s or " " in s[:13]:
            dt = datetime.fromisoformat(s.replace(" ", "T", 1) if " " in s and "T" not in s else s)
        else:
            dt = datetime.fromisoformat(s[:10] + "T00:00:00")
    except Exception:
        return str(iso_str)
    wd = _WEEKDAYS_KO[dt.weekday()]
    return f"{dt.month}월 {dt.day}일 ({wd}) {dt.strftime('%H:%M')}"


def event_at_to_date_prefix_ymd(event_at_iso: Optional[str]) -> str:
    """event_at ISO 문자열에서 YYYYMMDD 8자리 접두(신규 ID용)."""
    if not event_at_iso or not str(event_at_iso).strip():
        return datetime.now().strftime("%Y%m%d")
    s = str(event_at_iso).strip().replace("Z", "+00:00")
    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:4] + s[5:7] + s[8:10]
        dt = datetime.fromisoformat(s.replace(" ", "T", 1) if " " in s and "T" not in s else s)
        return dt.strftime("%Y%m%d")
    except Exception:
        return datetime.now().strftime("%Y%m%d")

ALLOWED_LIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "allowed_list.txt")


def parse_allowed_list_text(text: str) -> Dict[str, int]:
    """텍스트/CSV 한 덩어리를 {별명: 티켓수}로 파싱.
    한 줄: '별명 숫자' 또는 '별명,숫자' (공백·콤마 모두 허용)
    """
    allowed: Dict[str, int] = {}
    if not text or not str(text).strip():
        return allowed
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        if "," in line:
            parts = line.split(",", 1)
            name = parts[0].strip()
            try:
                tickets = int(parts[1].strip())
            except ValueError:
                tickets = 1
            allowed[unicodedata.normalize("NFC", name)] = tickets
            continue
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            try:
                tickets = int(float(parts[1]))
            except ValueError:
                tickets = 1
            allowed[unicodedata.normalize("NFC", name)] = tickets
        else:
            allowed[unicodedata.normalize("NFC", line)] = 1
    return allowed


def allowed_dict_to_lines(d: Dict[str, int]) -> str:
    if not d:
        return ""
    lines = []
    for name in sorted(d.keys(), key=lambda x: x.lower()):
        lines.append(f"{name}\t{d[name]}")
    return "\n".join(lines)


def normalize_event_id(key: Optional[str]) -> Optional[str]:
    """이벤트 식별자 정규화. evt- / YYYYMMDD+2자리 / YYMMDD-일련 그대로. 카페 URL만 canonical."""
    if not key:
        return key
    s = key.strip()
    if s.startswith("evt-"):
        return s
    if EVENT_ID_DATE_SERIAL_PATTERN.match(s):
        return s
    if EVENT_CODE_PATTERN.match(s):
        return s
    try:
        from standalone_comment_monitor.parsers import parse_post_ids_from_url

        clubid, articleid = parse_post_ids_from_url(s)
        if clubid and articleid:
            return f"https://cafe.naver.com/ca-fe/web/cafes/{clubid}/articles/{articleid}"
    except Exception:
        pass
    return s


# 하위 호환
normalize_url = normalize_event_id


def get_allowed_list(db, event_key: Optional[str] = None) -> Dict[str, int]:
    if not event_key:
        return {}
    try:
        _, _, _, _, _, _, _, _, allowed_list_content, _ = db.get_data(event_key)
        if allowed_list_content:
            return parse_allowed_list_text(allowed_list_content)
    except Exception as e:
        print(f"DEBUG: get_allowed_list DB error: {e}")
    return {}


def parse_participants_csv_bytes(data: bytes) -> Dict[str, int]:
    """CSV 바이트: 첫 열 별명, 둘째 열 티켓 (헤더 줄은 '이름' 등이면 스킵 시도)."""
    import csv
    import io

    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return {}
    start = 0
    if rows[0] and rows[0][0].strip().lower() in ("name", "별명", "닉네임", "nick"):
        start = 1
    out: Dict[str, int] = {}
    for row in rows[start:]:
        if not row or not str(row[0]).strip():
            continue
        name = str(row[0]).strip()
        tickets = 1
        if len(row) >= 2 and str(row[1]).strip():
            try:
                tickets = int(float(row[1].strip()))
            except ValueError:
                tickets = 1
        out[unicodedata.normalize("NFC", name)] = tickets
    return out
