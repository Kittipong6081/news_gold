"""
feeds.py
ดึงและ normalize ข่าวจากทุกแหล่ง ให้เป็นโครงสร้างเดียวกัน:

    {
        "id":        str,   # คีย์สำหรับกันซ้ำ (hash ของ guid/link/title)
        "source":    str,   # ชื่อแหล่งข่าว
        "title":     str,
        "summary":   str,
        "link":      str,
        "published": str,   # ISO8601 (อาจว่างได้)
        "published_dt": datetime | None,
        "impact":    str,   # เฉพาะ calendar ('High'/'Medium'/'Low') ไม่มีก็ ""
        "country":   str,   # เฉพาะ calendar
    }

รองรับ 2 ชนิด feed: "rss" (feedparser) และ "ff_calendar" (XML ของ Forex Factory)
ทุก network/parse error จะถูกจับและ log แล้วคืน [] เพื่อไม่ให้ loop หลักพัง
"""

import time
import hashlib
import logging
from datetime import datetime, timezone

import requests
import feedparser
import xml.etree.ElementTree as ET

import config

log = logging.getLogger("feeds")

# เวลาที่ดึงแต่ละ feed ล่าสุด (monotonic) สำหรับ throttle ต่อ feed
_last_fetch: dict[str, float] = {}


def _make_id(*parts: str) -> str:
    raw = "|".join(p for p in parts if p)
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:24]


def _http_get(url: str) -> bytes | None:
    """ดึง content ดิบ พร้อม header ปลอม browser และ timeout"""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": config.USER_AGENT, "Accept": "*/*"},
            timeout=config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as e:
        log.warning("ดึง feed ไม่สำเร็จ %s -> %s", url, e)
        return None


def _struct_to_iso(struct_time) -> tuple[str, datetime | None]:
    """แปลง time.struct_time ของ feedparser เป็น ISO string + datetime (UTC)"""
    if not struct_time:
        return "", None
    try:
        dt = datetime(*struct_time[:6], tzinfo=timezone.utc)
        return dt.isoformat(), dt
    except (ValueError, TypeError):
        return "", None


def _parse_ff_datetime(date_s: str, time_s: str) -> "datetime | None":
    """parse date+time ของ faireconomy calendar -> datetime (UTC, best-effort)
    คืน None ถ้าเป็น All Day / Tentative / Holiday หรือ parse ไม่ได้
    หมายเหตุ: feed ไม่ระบุ timezone ในตัว XML จึงถือเป็น UTC (อาจเพี้ยนหลัก ชม.)
    เราใช้คู่กับหน้าต่าง now ± MAX_AGE_HOURS จึงยังจับ event ได้แม้ TZ คลาดเล็กน้อย
    """
    if not date_s:
        return None
    t = (time_s or "").strip().lower().replace(" ", "")
    if not t or t in ("allday", "tentative", "holiday", "day1", "day2"):
        return None
    d = None
    for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            d = datetime.strptime(date_s.strip(), fmt)
            break
        except ValueError:
            continue
    if d is None:
        return None
    tt = None
    for fmt in ("%I:%M%p", "%I%p"):
        try:
            tt = datetime.strptime(t, fmt)
            break
        except ValueError:
            continue
    if tt is None:
        return None
    return d.replace(
        hour=tt.hour, minute=tt.minute, second=0, microsecond=0, tzinfo=timezone.utc
    )


# ---------------------------------------------------------------------------
# RSS / Atom มาตรฐาน
# ---------------------------------------------------------------------------
def _parse_rss(feed_cfg: dict) -> list[dict]:
    content = _http_get(feed_cfg["url"])
    if content is None:
        return []

    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        log.warning("feed %s parse มีปัญหา: %s", feed_cfg["name"], parsed.bozo_exception)
        return []

    items = []
    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        link = (entry.get("link") or "").strip()
        guid = (entry.get("id") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()

        # Google News (และ feed ที่มี <source>) บอกชื่อสำนักจริง เช่น Reuters/CNBC
        # -> ใช้เป็น "แหล่งข่าว" ที่แสดง แทนชื่อ feed เช่น "GoogleNews Gold"
        publisher = ""
        src = entry.get("source")
        if src:
            publisher = (src.get("title") or "").strip()
        # ตัด suffix " - Reuters" ท้ายพาดหัวออก ให้ AI ได้หัวข้อสะอาด
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -(len(publisher) + 3)].rstrip()
        display_source = publisher or feed_cfg["name"]

        published_iso, published_dt = _struct_to_iso(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )

        items.append(
            {
                "id": _make_id(guid, link, title),
                "source": display_source,
                "title": title,
                "summary": summary,
                "link": link,
                "published": published_iso,
                "published_dt": published_dt,
                "impact": "",
                "country": "",
            }
        )
    return items


# ---------------------------------------------------------------------------
# Forex Factory Economic Calendar (faireconomy XML)
# โครงสร้าง:
#   <weeklyevents>
#     <event>
#       <title>...</title><country>USD</country><date>...</date>
#       <time>...</time><impact>High</impact>
#       <forecast>...</forecast><previous>...</previous>
#     </event>
#   </weeklyevents>
# ---------------------------------------------------------------------------
def _parse_ff_calendar(feed_cfg: dict) -> list[dict]:
    content = _http_get(feed_cfg["url"])
    if content is None:
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        log.warning("parse XML ปฏิทิน %s ไม่สำเร็จ: %s", feed_cfg["name"], e)
        return []

    def txt(node, tag):
        el = node.find(tag)
        return (el.text or "").strip() if el is not None and el.text else ""

    now = datetime.now(timezone.utc)
    from datetime import timedelta
    window = timedelta(hours=config.MAX_AGE_HOURS)

    items = []
    for ev in root.findall(".//event"):
        title = txt(ev, "title")
        if not title:
            continue
        impact = txt(ev, "impact")
        # แจ้งเฉพาะข่าวแรงพอควร (High/Medium) -> ตัด noise + กัน flood
        if impact not in ("High", "Medium"):
            continue

        country = txt(ev, "country")
        date_s = txt(ev, "date")
        time_s = txt(ev, "time")
        forecast = txt(ev, "forecast")
        previous = txt(ev, "previous")

        # emit เฉพาะ event ที่กำหนดออกในช่วง now ± MAX_AGE_HOURS เท่านั้น
        # -> กัน flood ตอนไฟล์ปฏิทินรายสัปดาห์เปลี่ยน (id ใหม่ยกชุด)
        #    และให้เตือนใกล้เวลาจริงที่ตัวเลขออก  (All Day/Tentative จะถูกข้าม)
        scheduled = _parse_ff_datetime(date_s, time_s)
        if scheduled is None or not (now - window <= scheduled <= now + window):
            continue

        # ประกอบ title แบบมีบริบท เพื่อให้ keyword filter + AI เข้าใจ
        full_title = f"[{country}] {title}".strip()
        summary_parts = [f"Impact: {impact}"]
        if forecast:
            summary_parts.append(f"Forecast: {forecast}")
        if previous:
            summary_parts.append(f"Previous: {previous}")
        summary_parts.append(f"Scheduled: {scheduled.isoformat()}")
        summary = " | ".join(summary_parts)

        # id อิงจาก event+เวลา -> event เดิมรอบใหม่ไม่ส่งซ้ำ
        nid = _make_id(country, title, date_s, time_s)

        items.append(
            {
                "id": nid,
                "source": feed_cfg["name"],
                "title": full_title,
                "summary": summary,
                "link": "https://www.forexfactory.com/calendar",
                "published": scheduled.isoformat(),
                "published_dt": scheduled,
                "impact": impact,
                "country": country,
            }
        )
    return items


# ---------------------------------------------------------------------------
# API หลักของโมดูล
# ---------------------------------------------------------------------------
def fetch_one(feed_cfg: dict) -> list[dict]:
    try:
        if feed_cfg["type"] == "ff_calendar":
            return _parse_ff_calendar(feed_cfg)
        return _parse_rss(feed_cfg)
    except Exception as e:  # safety net กันทุกอย่างที่หลุดมา
        log.warning("ประมวลผล feed %s ล้มเหลว: %s", feed_cfg.get("name"), e)
        return []


def _is_due(feed_cfg: dict) -> bool:
    """เคารพ min_interval ต่อ feed (กันยิงถี่จนโดน 429)"""
    min_interval = feed_cfg.get("min_interval", 0)
    if min_interval <= 0:
        return True
    last = _last_fetch.get(feed_cfg["name"], 0.0)
    return (time.monotonic() - last) >= min_interval


def fetch_all() -> list[dict]:
    """ดึงทุก feed (ที่ถึงรอบ) รวมเป็น list เดียว (กันซ้ำในรอบเดียวกันด้วย id)"""
    seen_ids = set()
    all_items = []
    for feed_cfg in config.FEEDS:
        if not _is_due(feed_cfg):
            continue  # ยังไม่ถึงรอบของ feed นี้ -> ข้าม
        items = fetch_one(feed_cfg)
        _last_fetch[feed_cfg["name"]] = time.monotonic()
        log.debug("feed %s -> %d รายการ", feed_cfg["name"], len(items))
        for it in items:
            if it["id"] in seen_ids:
                continue
            seen_ids.add(it["id"])
            all_items.append(it)
    return all_items
