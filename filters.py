"""
filters.py
ตรรกะการคัดกรองข่าวก่อนส่งให้ AI (เพื่อประหยัด Token)
- ด่านอายุข่าว: ทิ้งข่าวเก่าเกิน MAX_AGE_HOURS (เฉพาะข่าวที่มี timestamp)
- ด่าน Keyword: ต้องมีคำที่เกี่ยวกับทอง/มาโคร ในหัวข้อหรือสรุป
- ข่าวปฏิทิน (calendar) ที่ Impact = High/Medium ให้ผ่านอัตโนมัติ (เป็นข่าวสำคัญเสมอ)

หมายเหตุ: ด่านกันซ้ำ (de-dup) อยู่ใน main.py ที่คุยกับ storage โดยตรง
"""

import logging
from datetime import datetime, timezone, timedelta

import config

log = logging.getLogger("filters")


def is_recent(item: dict) -> bool:
    """ข่าวที่ไม่มี timestamp ให้ถือว่าผ่าน (เช่น calendar) ; ที่มี ต้องไม่เก่าเกินกำหนด"""
    dt = item.get("published_dt")
    if dt is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.MAX_AGE_HOURS)
    return dt >= cutoff


def matches_keywords(item: dict) -> bool:
    """ตรวจ keyword ในหัวข้อ + สรุป"""
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    return bool(config.KEYWORD_REGEX.search(text))


# สกุลเงินที่มีผลต่อทองคำมากที่สุด (ทองตั้งราคาเป็น USD)
_GOLD_RELEVANT_COUNTRIES = {"USD", "ALL", ""}
# ระดับ impact ที่จะแจ้ง (High = ขยับทองชัด, Medium = มีผลปานกลาง)
_CALENDAR_IMPACTS = {"high", "medium"}


def is_relevant_calendar(item: dict) -> bool:
    """
    ข่าวปฏิทินที่ "สำคัญพอจะแจ้ง" = Impact High/Medium ของฝั่ง USD/All
    (เช่น FOMC, NFP, CPI, PPI, Retail Sales, GDP — ตัวที่ขยับทองจริง)
    คัดสกุลเงินอื่น/ตัวเลข Low ออก เพื่อไม่ให้ token บานปลายตอน feed รายสัปดาห์รีเซ็ต

    หมายเหตุ: ไม่ใช้ matches_keywords กับข่าวปฏิทิน เพราะหัวข้อมีรหัสสกุลเงิน
    เช่น "[USD] ..." ซึ่งจะไปแมตช์ keyword 'usd' ทำให้ทุก event ผ่านโดยไม่ตั้งใจ
    """
    impact = item.get("impact", "").lower()
    country = item.get("country", "").upper()
    return impact in _CALENDAR_IMPACTS and country in _GOLD_RELEVANT_COUNTRIES


def passes(item: dict) -> bool:
    """รวมทุกด่าน -> True = ส่งต่อให้ AI ได้"""
    if not is_recent(item):
        return False
    # แยกเส้นทางข่าวปฏิทิน (มีฟิลด์ impact) ออกจากข่าว RSS ทั่วไป
    if item.get("impact"):
        return is_relevant_calendar(item)
    return matches_keywords(item)
