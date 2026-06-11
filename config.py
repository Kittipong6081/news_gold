"""
config.py
ศูนย์รวมการตั้งค่าทั้งหมดของระบบ XAUUSD News Monitor
- โหลด Environment Variables
- รายการ RSS Feeds
- Keyword สำหรับกรองข่าว
- พารามิเตอร์การทำงาน (รอบ polling, อายุข่าว ฯลฯ)

แก้รายการ FEEDS / KEYWORDS ที่นี่ที่เดียวพอ
"""

import os
import re
from dotenv import load_dotenv

# โหลดค่าจากไฟล์ .env (ถ้ามี) — บน Cloud จะใช้ Env Vars ของแพลตฟอร์มแทน
load_dotenv()

# ---------------------------------------------------------------------------
# 1) Secrets / Environment Variables
# ---------------------------------------------------------------------------
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# โมเดลที่ใช้ — gpt-4o-mini ถูกและเร็ว เหมาะกับงานแปล+จัดหมวดหัวข้อข่าว
# เปลี่ยนได้ผ่าน env OPENAI_MODEL (เช่นจะลองรุ่นใหม่กว่าก็ตั้งค่าได้เลย)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# ---------------------------------------------------------------------------
# 2) พฤติกรรมการทำงาน
# ---------------------------------------------------------------------------
# รอบการดึงข่าว (วินาที) — โจทย์กำหนดทุก 1 นาที
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# พิจารณาเฉพาะข่าวที่เผยแพร่ภายใน N ชั่วโมงล่าสุด (กันข่าวเก่าโผล่มาตอนเพิ่ม feed)
MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "6"))

# จำนวนการแจ้งเตือนสูงสุดต่อ 1 รอบ (กัน Discord โดน flood เวลาข่าวเข้าพร้อมกันเยอะ ๆ)
MAX_ALERTS_PER_CYCLE = int(os.getenv("MAX_ALERTS_PER_CYCLE", "8"))

# แจ้งเตือนเฉพาะข่าวที่ impact ตั้งแต่ระดับนี้ขึ้นไป
#   "Low"    = แจ้งทุกระดับ
#   "Medium" = ตัดข่าว Low ทิ้ง (ค่าเริ่มต้น — กรองข่าวจิ๊บจ๊อยออก)
#   "High"   = แจ้งเฉพาะข่าวแรงเท่านั้น
ALERT_MIN_IMPACT = os.getenv("ALERT_MIN_IMPACT", "Medium").strip().capitalize()

_IMPACT_RANK = {"low": 1, "medium": 2, "high": 3}


def impact_rank(level: str) -> int:
    """แปลงระดับ impact เป็นตัวเลขเพื่อเทียบ (ไม่รู้จัก = ถือเป็น Low)"""
    return _IMPACT_RANK.get((level or "").strip().lower(), 1)

# ที่อยู่ไฟล์ฐานข้อมูล SQLite สำหรับเก็บประวัติข่าว (ด่านกันซ้ำ)
# บน Cloud ที่ filesystem ลบทุกครั้งที่ deploy ให้ชี้ไป persistent disk เช่น /data/seen.db
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "seen_news.db"))

# Timeout ของการดึง HTTP แต่ละครั้ง (วินาที)
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))

# User-Agent ปลอมตัวเป็น browser ทั่วไป กัน feed บางเจ้าตอบ 403
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# 3) รายการ RSS / Data Feeds
#    type:
#      "rss"          -> RSS/Atom มาตรฐาน (ใช้ feedparser)
#      "ff_calendar"  -> XML ปฏิทินข่าวของ Forex Factory (faireconomy) parse เอง
#
#    หมายเหตุ: feed ไหนล่ม/โดนบล็อก ระบบจะ log แล้วข้ามไป ไม่ทำให้ทั้งระบบพัง
#    เสาหลักที่ฟรี+เสถียรที่สุดคือ Forex Factory calendar + Google News RSS
# ---------------------------------------------------------------------------
FEEDS = [
    # --- ข่าวในตาราง (Economic Calendar) ของ Forex Factory ---
    # faireconomy จำกัด rate แรง + ปฏิทินรายสัปดาห์ไม่เปลี่ยนทุกนาที
    # จึงตั้ง min_interval ให้ดึงทุก 10 นาที (กัน 429)
    {
        "name": "ForexFactory Calendar",
        "url": "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",
        "type": "ff_calendar",
        "min_interval": 600,
    },

    # --- Google News RSS (ฟรี ไม่ต้อง auth เสถียรมาก ใช้แทน Reuters/Bloomberg ที่ปิด RSS ฟรีไปแล้ว) ---
    # when:1d = เอาเฉพาะข่าว 1 วันล่าสุด ช่วยลดปริมาณ
    {
        "name": "GoogleNews Gold",
        "url": "https://news.google.com/rss/search?q=gold+price+OR+XAUUSD+when:1d&hl=en-US&gl=US&ceid=US:en",
        "type": "rss",
    },
    {
        "name": "GoogleNews Fed/Macro",
        "url": "https://news.google.com/rss/search?q=(Fed+OR+FOMC+OR+inflation+OR+CPI+OR+%22interest+rate%22)+when:1d&hl=en-US&gl=US&ceid=US:en",
        "type": "rss",
    },
    {
        "name": "GoogleNews Geopolitics",
        "url": "https://news.google.com/rss/search?q=(war+OR+geopolitical+OR+sanctions+OR+%22safe+haven%22)+when:1d&hl=en-US&gl=US&ceid=US:en",
        "type": "rss",
    },

    # --- แหล่งข่าวสายเศรษฐกิจ/ฟอเร็กซ์เพิ่มเติม ---
    {
        "name": "FXStreet News",
        "url": "https://www.fxstreet.com/rss/news",
        "type": "rss",
    },
    {
        "name": "MarketWatch Top Stories",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "type": "rss",
    },
    {
        "name": "Investing.com Commodities",
        "url": "https://www.investing.com/rss/news_285.rss",
        "type": "rss",
    },
    # Reuters/Bloomberg ปิด RSS ฟรีแล้ว -> ดึงเนื้อหาผ่าน Google News แทน
    {
        "name": "Reuters (via GoogleNews)",
        "url": "https://news.google.com/rss/search?q=(gold+OR+Fed+OR+inflation)+site:reuters.com+when:1d&hl=en-US&gl=US&ceid=US:en",
        "type": "rss",
    },
    # หากต้องการเพิ่ม Financial Juice / TradingView ฯลฯ ใส่บรรทัดเพิ่มได้เลย
]

# ---------------------------------------------------------------------------
# 4) Keyword Filter (ด่านที่ 2)
#    มีคำเหล่านี้ในหัวข้อ/สรุปข่าว -> ผ่าน  | ไม่มี -> ปัดตก (ไม่ส่งให้ AI)
#    ครอบคลุมทั้ง EN และคำไทยที่อาจเจอใน feed ไทย
# ---------------------------------------------------------------------------
KEYWORDS = [
    # ทองคำ
    r"gold", r"\bxau\b", r"xauusd", r"bullion", r"precious metal", r"ทองคำ", r"ราคาทอง",
    # ธนาคารกลาง / นโยบายการเงิน
    r"\bfed\b", r"federal reserve", r"fomc", r"powell", r"interest rate", r"rate cut",
    r"rate hike", r"monetary policy", r"hawkish", r"dovish", r"ecb", r"central bank",
    # เงินเฟ้อ / ตัวเลขเศรษฐกิจ
    r"inflation", r"\bcpi\b", r"\bppi\b", r"\bpce\b", r"non-?farm", r"\bnfp\b",
    r"payroll", r"unemployment", r"\bgdp\b", r"recession", r"jobless",
    # ค่าเงิน / พันธบัตร
    r"us dollar", r"\busd\b", r"dollar index", r"\bdxy\b", r"treasury", r"bond yield",
    r"yields?",
    # ความเสี่ยง / ภูมิรัฐศาสตร์ / วิกฤต
    r"\bwar\b", r"geopolitical", r"conflict", r"sanction", r"safe[- ]haven",
    r"crisis", r"tariff", r"middle east",
]

# รวม keyword เป็น regex เดียว (case-insensitive) เพื่อความเร็ว
KEYWORD_REGEX = re.compile("|".join(KEYWORDS), re.IGNORECASE)


def validate_config() -> list[str]:
    """ตรวจค่าที่จำเป็น คืน list ของข้อผิดพลาด (ว่าง = ผ่าน)"""
    errors = []
    if not DISCORD_WEBHOOK_URL:
        errors.append("ยังไม่ได้ตั้งค่า DISCORD_WEBHOOK_URL")
    if not OPENAI_API_KEY:
        errors.append("ยังไม่ได้ตั้งค่า OPENAI_API_KEY")
    return errors
