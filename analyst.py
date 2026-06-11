"""
analyst.py
ชั้นวิเคราะห์ด้วย AI (OpenAI) — เรียกเฉพาะข่าวที่ผ่านการกรองแล้วเท่านั้น
- แปลหัวข้อเป็นไทย + ประเมินผลกระทบ + ทิศทางทอง + บทวิเคราะห์สั้น
- บังคับ output เป็น JSON (response_format=json_object) เพื่อ parse ได้ชัวร์
- มี retry + fallback กัน error จาก API
"""

import json
import logging
import time

from openai import OpenAI
import config

log = logging.getLogger("analyst")

_client = OpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None

# ค่าที่ AI ต้องเลือกให้อยู่ในกรอบ (ใช้ validate ผลลัพธ์)
VALID_IMPACT = {"High", "Medium", "Low"}
VALID_DIRECTION = {"ขึ้นแรง", "ขึ้นปานกลาง", "ลงแรง", "ลงปานกลาง", "ไม่กระทบ"}

SYSTEM_PROMPT = """คุณคือนักวิเคราะห์ทองคำ (XAUUSD) มืออาชีพ
หน้าที่: อ่านข่าวภาษาอังกฤษ แล้วสรุปผลกระทบต่อราคาทองคำเป็นภาษาไทยแบบกระชับ

ตรรกะหลักของทองคำ:
- ดอลลาร์แข็ง / ดอกเบี้ยขึ้น / Fed สาย hawkish / ตัวเลขเศรษฐกิจสหรัฐแข็งแกร่ง (CPI สูง, NFP ดี) -> ทองมักลง
- ดอกเบี้ยลด / Fed สาย dovish / เงินเฟ้อชะลอ / เศรษฐกิจอ่อนแอ -> ทองมักขึ้น
- สงคราม / ความขัดแย้งภูมิรัฐศาสตร์ / วิกฤตการเงิน / ความไม่แน่นอนสูง (safe-haven) -> ทองมักขึ้น
- ข่าวที่ไม่เกี่ยวกับทอง/ดอลลาร์/ดอกเบี้ย/ความเสี่ยง -> ไม่กระทบ

สำคัญที่สุด: ประเมินอย่าง "เข้มงวด" ว่าข่าวนี้คุ้มที่จะเตือนเทรดเดอร์ทองหรือไม่ (should_alert)
หลักคิด: ถ้าไม่มั่นใจ ให้ should_alert = false ไว้ก่อน (เตือนน้อยแต่ตรงดีกว่าเตือนจุกจิก)
- should_alert = true เฉพาะข่าว "ระดับขยับตลาด" ที่เทรดเดอร์ต้องรู้ทันที เช่น
  ตัวเลขเศรษฐกิจสำคัญที่ออก "ต่างจากที่คาด" ชัด (CPI/NFP/GDP/PCE),
  การตัดสินใจหรือถ้อยแถลงของ Fed/ประธาน Fed ที่เปลี่ยนมุมมองดอกเบี้ย,
  เหตุการณ์ฉุกเฉิน/สงคราม/วิกฤตที่ดันแรงซื้อ safe-haven
- should_alert = false เสมอ สำหรับ: บทวิเคราะห์/บทความความเห็น/คอลัมน์,
  สรุปตลาดรายวัน/รายสัปดาห์, บทคาดการณ์ล่วงหน้า (preview), เทคนิคอลรายวัน,
  ข่าวที่ตัวเลขออกตรงตามคาด (price-in แล้ว), ราคาทองขยับเล็กน้อยตามปกติ,
  ข่าวซ้ำ/เก่า, หรือข่าวที่ทองน่าจะ "นิ่ง"

ตอบกลับเป็น JSON object เท่านั้น ตาม schema นี้ (ห้ามมีข้อความอื่นนอก JSON):
{
  "headline_th": "หัวข้อข่าวแปลไทยสั้นกระชับ",
  "impact": "High | Medium | Low",
  "direction": "ขึ้นแรง | ขึ้นปานกลาง | ลงแรง | ลงปานกลาง | ไม่กระทบ",
  "analysis_th": "บทวิเคราะห์สั้น ไม่เกิน 2 ประโยค บอกเหตุผลว่าทำไมทองจะไปทิศทางนั้น",
  "should_alert": true หรือ false (ข่าวนี้ควรเตือนเทรดเดอร์ทองไหม)
}"""


def _fallback(item: dict, reason: str) -> dict:
    """ผลลัพธ์สำรองเมื่อ AI ใช้ไม่ได้ — อย่างน้อยยังได้แจ้งเตือนหัวข้อข่าว"""
    log.warning("ใช้ fallback สำหรับ '%s' (%s)", item.get("title", "")[:60], reason)
    return {
        "headline_th": item.get("title", "")[:200],
        "impact": "Medium" if item.get("impact", "").lower() == "high" else "Low",
        "direction": "ไม่กระทบ",
        "analysis_th": "(วิเคราะห์อัตโนมัติไม่สำเร็จ — แสดงหัวข้อข่าวดิบ)",
        # AI ใช้ไม่ได้ -> แจ้งเฉพาะข่าวปฏิทินแรง (High) ที่พลาดไม่ได้ ที่เหลือเงียบไว้
        "should_alert": item.get("impact", "").lower() == "high",
        "_fallback": True,
    }


def _validate(data: dict, item: dict) -> dict:
    """กันกรณี AI ตอบนอกกรอบ -> บีบให้อยู่ในค่าที่ถูกต้อง"""
    out = {
        "headline_th": str(data.get("headline_th") or item.get("title", ""))[:300],
        "impact": data.get("impact", "Low"),
        "direction": data.get("direction", "ไม่กระทบ"),
        "analysis_th": str(data.get("analysis_th") or "")[:500],
        "_fallback": False,
    }
    if out["impact"] not in VALID_IMPACT:
        out["impact"] = "Low"
    if out["direction"] not in VALID_DIRECTION:
        out["direction"] = "ไม่กระทบ"

    # should_alert: AI ตัดสินว่าข่าวนี้ควรเตือนไหม (รับได้ทั้ง bool และ string)
    should = data.get("should_alert")
    if isinstance(should, str):
        should = should.strip().lower() in ("true", "yes", "1", "ควร", "แจ้ง")
    out["should_alert"] = True if should is None else bool(should)
    return out


def _strip_unsupported_param(params: dict, err: Exception) -> "str | None":
    """ถ้า API ฟ้องว่า param ไหนไม่รองรับ ให้ถอดออกจาก params แล้วคืนชื่อ param นั้น
    รองรับโมเดลรุ่นใหม่ (เช่น gpt-5.x) ที่ deprecate max_tokens / จำกัด temperature ฯลฯ
    -> ไม่ต้องแก้โค้ดเองเวลาเปลี่ยนโมเดล"""
    body = getattr(err, "body", None)
    param = None
    if isinstance(body, dict):
        param = (body.get("error") or {}).get("param")
    if not param:  # เผื่อ SDK ไม่ส่ง param มา -> เดาจากข้อความ error
        msg = str(err)
        for cand in ("temperature", "max_tokens", "max_completion_tokens", "response_format"):
            if cand in msg and cand in params:
                param = cand
                break
    if param and param in params:
        params.pop(param, None)
        return param
    return None


def analyze(item: dict, max_retries: int = 2) -> dict:
    """วิเคราะห์ข่าว 1 ชิ้น คืน dict ที่พร้อมส่ง Discord"""
    if _client is None:
        return _fallback(item, "ไม่มี OPENAI_API_KEY")

    # ส่งเฉพาะที่จำเป็น + ตัดสรุปให้สั้น เพื่อประหยัด token
    summary = (item.get("summary") or "")[:600]
    user_content = (
        f"แหล่งข่าว: {item.get('source', '')}\n"
        f"หัวข้อ: {item.get('title', '')}\n"
        f"รายละเอียด: {summary}"
    )

    # max_completion_tokens = พารามิเตอร์ใหม่ (ใช้ได้ทั้ง gpt-4o-mini และ gpt-5.x)
    # ถ้าโมเดลไม่รับ temperature/param ใด จะถูกถอดออกอัตโนมัติแล้วลองใหม่
    params = {
        "model": config.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "max_completion_tokens": 350,
        "response_format": {"type": "json_object"},
    }

    last_err = None
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            resp = _client.chat.completions.create(**params)
            data = json.loads(resp.choices[0].message.content)
            return _validate(data, item)
        except json.JSONDecodeError as e:
            last_err = e
            log.warning("AI ตอบ JSON ไม่ถูกต้อง (รอบ %d): %s", attempt, e)
        except Exception as e:  # rate limit / network / auth / param ไม่รองรับ
            last_err = e
            removed = _strip_unsupported_param(params, e)
            if removed:
                log.info("โมเดลไม่รองรับ '%s' — ถอดออกแล้วลองใหม่ทันที", removed)
                attempt -= 1  # ไม่นับเป็น retry จริง (เป็นการปรับ param)
                continue
            log.warning("เรียก OpenAI ล้มเหลว (รอบ %d): %s", attempt, e)
            time.sleep(min(2 ** attempt, 8))  # exponential backoff

    return _fallback(item, f"หมด retry: {last_err}")
