"""
storage.py
ด่านที่ 1: De-duplication ด้วย SQLite
- จำ id ของข่าวที่เคยประมวลผลแล้ว เพื่อไม่ส่งซ้ำให้ AI / Discord
- มี meta flag สำหรับ "cold start seeding" (ครั้งแรกที่รัน ไม่ยิงแจ้งเตือนย้อนหลัง)

ใช้ context manager เปิด/ปิด connection ทุกครั้ง -> thread-safe พอสำหรับ loop เดี่ยว
และทนทานต่อการ restart
"""

import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

log = logging.getLogger("storage")


class NewsStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_news (
                    id           TEXT PRIMARY KEY,
                    source       TEXT,
                    title        TEXT,
                    link         TEXT,
                    published    TEXT,
                    processed_at TEXT
                )
                """
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
            )
            # เก็บ "ลายเซ็นหัวข้อข่าว" ที่เพิ่งแจ้งไป -> กันข่าวเดียวกันจากหลายสำนักเด้งซ้ำ
            conn.execute(
                "CREATE TABLE IF NOT EXISTS alerted_titles (sig TEXT PRIMARY KEY, ts TEXT)"
            )
        log.info("ฐานข้อมูลพร้อมใช้งานที่ %s", self.db_path)

    # ----- De-duplication -----
    def is_seen(self, news_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_news WHERE id = ? LIMIT 1", (news_id,)
            ).fetchone()
            return row is not None

    def mark_seen(self, item: dict):
        """บันทึกว่าเคยเจอข่าวนี้แล้ว (เรียกทั้งกรณีส่งและกรณีโดนกรองทิ้ง)"""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO seen_news (id, source, title, link, published, processed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    item.get("source", ""),
                    item.get("title", "")[:500],
                    item.get("link", ""),
                    item.get("published", ""),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM seen_news").fetchone()[0]

    # ----- กันข่าวซ้ำตามความคล้ายหัวข้อ (cross-source) -----
    def recent_similar_title(self, sig: str, hours: int) -> bool:
        """True ถ้ามีข่าวหัวข้อคล้ายกันนี้ถูกแจ้งไปแล้วภายใน N ชั่วโมง"""
        if not sig:
            return False
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM alerted_titles WHERE sig = ? AND ts >= ? LIMIT 1",
                (sig, cutoff),
            ).fetchone()
            return row is not None

    def remember_title(self, sig: str):
        """บันทึกลายเซ็นหัวข้อที่เพิ่งประมวลผล/แจ้งไป"""
        if not sig:
            return
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO alerted_titles (sig, ts) VALUES (?, ?)",
                (sig, datetime.now(timezone.utc).isoformat()),
            )

    def purge_older_than(self, days: int = 7):
        """ลบประวัติเก่ากว่า N วัน กันไฟล์ DB โตไม่จำกัด"""
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        with self._conn() as conn:
            # processed_at เป็น ISO string เทียบแบบ lexicographic ได้
            cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
            cur = conn.execute(
                "DELETE FROM seen_news WHERE processed_at < ?", (cutoff_iso,)
            )
            conn.execute("DELETE FROM alerted_titles WHERE ts < ?", (cutoff_iso,))
            if cur.rowcount:
                log.info("ล้างประวัติข่าวเก่า %d รายการ", cur.rowcount)

    # ----- Cold start flag -----
    def is_seeded(self) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'seeded'"
            ).fetchone()
            return row is not None and row[0] == "1"

    def set_seeded(self):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('seeded', '1')"
            )
