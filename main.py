"""
main.py
ตัวควบคุมหลัก (Orchestrator) — รันลูปไม่รู้จบ
ลำดับงานต่อ 1 รอบ:
    1) ดึงข่าวทุก feed
    2) ด่านที่ 1: ข้ามข่าวที่เคยเห็น (de-dup ผ่าน SQLite)
    3) ด่านที่ 2: กรอง keyword + อายุข่าว (ไม่ผ่าน = mark seen แล้วทิ้ง ไม่ส่ง AI)
    4) ส่งข่าวที่ผ่าน -> AI วิเคราะห์ -> Discord
    5) mark seen ทุกชิ้นที่ประมวลผลแล้ว

Cold start: รอบแรกสุด (DB ยังไม่ seed) จะ mark ข่าวปัจจุบันทั้งหมดว่า seen เงียบ ๆ
ไม่ยิงแจ้งเตือนย้อนหลัง -> กัน Discord ระเบิดตอนเพิ่งเปิดเครื่อง/หลัง redeploy
"""

import sys
import time
import signal
import logging

import config
from storage import NewsStore
from feeds import fetch_all
import filters
import analyst
import notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("main")

_running = True


def _handle_stop(signum, frame):
    global _running
    log.info("ได้รับสัญญาณหยุด (%s) — กำลังปิดอย่างนุ่มนวล...", signum)
    _running = False


def cold_start_seed(store: NewsStore):
    """รอบแรก: บันทึกข่าวปัจจุบันทั้งหมดว่าเห็นแล้ว โดยไม่แจ้งเตือน"""
    log.info("Cold start: กำลัง seed ข่าวปัจจุบันเพื่อกันแจ้งเตือนย้อนหลัง...")
    items = fetch_all()
    for it in items:
        store.mark_seen(it)
    store.set_seeded()
    log.info("Cold start เสร็จ: seed ไป %d รายการ", len(items))


def run_cycle(store: NewsStore):
    items = fetch_all()
    if not items:
        log.debug("รอบนี้ไม่มีข่าว")
        return

    new_items = [it for it in items if not store.is_seen(it["id"])]
    if not new_items:
        return
    log.info("พบข่าวใหม่ %d รายการ (จากทั้งหมด %d)", len(new_items), len(items))

    alerts_sent = 0
    for it in new_items:
        try:
            if not filters.passes(it):
                store.mark_seen(it)  # เห็นแล้ว แต่ไม่เกี่ยว -> จำไว้ไม่ต้องเช็คซ้ำ
                continue

            if alerts_sent >= config.MAX_ALERTS_PER_CYCLE:
                log.warning("ถึงเพดานแจ้งเตือน/รอบ (%d) — ที่เหลือรอรอบถัดไป",
                            config.MAX_ALERTS_PER_CYCLE)
                break  # ที่เหลือยังไม่ mark seen -> ค่อยมาเอารอบหน้า

            analysis = analyst.analyze(it)          # ด่าน AI (เสีย token เฉพาะตรงนี้)

            # ด่าน AI ดุลพินิจ: ข่าวนี้ "ควรเตือนผู้ใช้ไหม" (ตัดข่าวที่ทองน่าจะนิ่ง/price-in)
            if not analysis.get("should_alert", True):
                log.info("AI ประเมินว่าไม่จำเป็นต้องแจ้ง (ทองน่าจะนิ่ง): %s",
                         it.get("title", "")[:60])
                store.mark_seen(it)
                continue

            # ด่านสุดท้าย: ตัดข่าว impact ต่ำกว่าเกณฑ์ทิ้ง (เช่น Low) -> ไม่แจ้งเตือน
            if config.impact_rank(analysis["impact"]) < config.impact_rank(config.ALERT_MIN_IMPACT):
                log.info("ข้ามข่าว impact=%s (ต่ำกว่า %s): %s",
                         analysis["impact"], config.ALERT_MIN_IMPACT, it.get("title", "")[:60])
                store.mark_seen(it)
                continue

            ok = notifier.send(it, analysis)        # ส่ง Discord
            store.mark_seen(it)
            if ok:
                alerts_sent += 1
            time.sleep(0.5)  # เว้นจังหวะกัน Discord rate limit
        except Exception as e:
            log.exception("ประมวลผลข่าวล้มเหลว '%s': %s", it.get("title", "")[:60], e)
            store.mark_seen(it)  # กัน loop ติดข่าวเดิม

    if alerts_sent:
        log.info("รอบนี้ส่งแจ้งเตือน %d รายการ", alerts_sent)


def main():
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    errors = config.validate_config()
    if errors:
        for e in errors:
            log.error("Config ผิดพลาด: %s", e)
        log.error("ตั้งค่า Environment Variables ให้ครบก่อนรัน")
        sys.exit(1)

    log.info("=== XAUUSD News Monitor เริ่มทำงาน ===")
    log.info("โมเดล AI: %s | รอบ polling: %ds | feeds: %d",
             config.OPENAI_MODEL, config.POLL_INTERVAL_SECONDS, len(config.FEEDS))

    store = NewsStore(config.DB_PATH)

    if not store.is_seeded():
        cold_start_seed(store)
        notifier.send_text("🟢 **XAUUSD News Monitor ออนไลน์** — เริ่มเฝ้าข่าวแล้ว")

    cycle = 0
    while _running:
        cycle += 1
        try:
            run_cycle(store)
            if cycle % 60 == 0:  # ทุก ~1 ชม. ล้างประวัติเก่า
                store.purge_older_than(days=7)
        except Exception as e:
            log.exception("รอบ %d ล้มเหลว: %s", cycle, e)

        # นอนทีละน้อยเพื่อให้ตอบสนองสัญญาณหยุดได้ไว
        slept = 0
        while _running and slept < config.POLL_INTERVAL_SECONDS:
            time.sleep(1)
            slept += 1

    log.info("=== ปิดระบบเรียบร้อย ===")


if __name__ == "__main__":
    main()
