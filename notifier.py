"""
notifier.py
ส่งผลวิเคราะห์เข้า Discord ผ่าน Webhook
- ใช้ Embed ให้สวย + แถบสีตามทิศทางทอง
- จัดฟอร์แมต Markdown ตามที่โจทย์กำหนด
- จัดการ rate limit (429) ด้วยการรอตาม retry_after
"""

import logging
import time

import requests
import config

log = logging.getLogger("notifier")

# สีแถบ embed ตามทิศทาง
_COLOR = {
    "ขึ้นแรง": 0x1F8B4C,      # เขียวเข้ม
    "ขึ้นปานกลาง": 0x2ECC71,  # เขียว
    "ลงแรง": 0xC0392B,       # แดงเข้ม
    "ลงปานกลาง": 0xE74C3C,   # แดง
    "ไม่กระทบ": 0x95A5A6,     # เทา
}

_IMPACT_EMOJI = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}


def _build_payload(item: dict, analysis: dict) -> dict:
    direction = analysis.get("direction", "ไม่กระทบ")
    impact = analysis.get("impact", "Low")
    color = _COLOR.get(direction, 0x95A5A6)
    impact_label = f"{_IMPACT_EMOJI.get(impact, '')} {impact}".strip()

    # ข้อความ Markdown ตามรูปแบบที่โจทย์กำหนด (ใส่ใน description ของ embed)
    description = (
        f"**หัวข้อข่าว:** {analysis.get('headline_th', '')}\n"
        f"**ระดับผลกระทบ:** {impact_label}\n"
        f"**ทิศทางทอง:** {direction}\n"
        f"**บทวิเคราะห์สั้น:** {analysis.get('analysis_th', '')}"
    )

    embed = {
        "title": "🔔 [XAUUSD NEWS ALERT]",
        "description": description,
        "color": color,
        "footer": {"text": f"แหล่งข่าว: {item.get('source', '')}"},
    }
    link = item.get("link")
    if link:
        embed["url"] = link

    return {"embeds": [embed]}


def send(item: dict, analysis: dict, max_retries: int = 3) -> bool:
    """ส่งแจ้งเตือน 1 ข่าว คืน True ถ้าสำเร็จ"""
    if not config.DISCORD_WEBHOOK_URL:
        log.error("ไม่มี DISCORD_WEBHOOK_URL — ข้ามการส่ง")
        return False

    payload = _build_payload(item, analysis)

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                config.DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=config.HTTP_TIMEOUT,
            )
            # Discord rate limit
            if resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 1)
                log.warning("Discord rate limit รอ %.1fs", retry_after)
                time.sleep(float(retry_after) + 0.5)
                continue
            resp.raise_for_status()
            log.info("ส่งแจ้งเตือนแล้ว: %s", analysis.get("headline_th", "")[:60])
            return True
        except requests.RequestException as e:
            log.warning("ส่ง Discord ล้มเหลว (รอบ %d): %s", attempt, e)
            time.sleep(min(2 ** attempt, 8))

    log.error("ส่ง Discord ไม่สำเร็จหลังลอง %d ครั้ง", max_retries)
    return False


def send_text(message: str) -> bool:
    """ส่งข้อความธรรมดา (ใช้แจ้งสถานะระบบ เช่น บูตเครื่อง / error)"""
    if not config.DISCORD_WEBHOOK_URL:
        return False
    try:
        resp = requests.post(
            config.DISCORD_WEBHOOK_URL,
            json={"content": message[:1900]},
            timeout=config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.warning("ส่งข้อความสถานะล้มเหลว: %s", e)
        return False
