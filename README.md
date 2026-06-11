# 🥇 XAUUSD Real-time News Monitor & AI Analyst

ระบบเฝ้าข่าวทองคำ (XAUUSD) อัตโนมัติ 24/7 — ดึงข่าวเอง กรองเอง วิเคราะห์ด้วย AI แล้วแจ้งเข้า Discord
ออกแบบให้ **ประหยัด Token** ด้วยการกรองข่าว 2 ด่าน *ก่อน* ส่งให้ AI

```
RSS Feeds ──> [ด่าน 1: กันซ้ำ (SQLite)] ──> [ด่าน 2: Keyword + อายุข่าว] ──> AI (OpenAI) ──> Discord
              ทิ้งข่าวที่เคยเห็น              ทิ้งข่าวที่ไม่เกี่ยวกับทอง        เสีย token เฉพาะข่าวที่ผ่าน
```

> 💡 **หัวใจการประหยัดเงิน:** ข่าวจะถูกส่งให้ OpenAI **ก็ต่อเมื่อ** เป็นข่าวใหม่ (ไม่ซ้ำ) **และ** มี keyword ที่เกี่ยวกับทอง/เศรษฐกิจมหภาคเท่านั้น ข่าวที่ไม่เกี่ยวถูกปัดตกในโค้ดฟรี ๆ

---

## 📁 โครงสร้างโปรเจกต์

| ไฟล์ | หน้าที่ |
|------|---------|
| `config.py` | ศูนย์รวม config: env, รายการ feeds, keyword, พารามิเตอร์ |
| `storage.py` | **ด่าน 1** — SQLite จำข่าวที่เคยประมวลผล (de-dup) + flag cold start |
| `feeds.py` | ดึง & normalize ข่าวจาก RSS + ปฏิทิน Forex Factory |
| `filters.py` | **ด่าน 2** — กรอง keyword + อายุข่าว |
| `analyst.py` | เรียก OpenAI วิเคราะห์ตรรกะทอง คืน JSON |
| `notifier.py` | ส่ง Discord Webhook (embed สวย + แถบสีตามทิศทาง) |
| `main.py` | ลูปหลักทุก 60 วิ ร้อยทุกอย่างเข้าด้วยกัน |
| `requirements.txt` | รายการ library |
| `.env.example` | ตัวอย่างการตั้งค่า secret |
| `Procfile` / `render.yaml` | ไฟล์ deploy ขึ้น Cloud |

---

## 🚀 รันบนเครื่องตัวเอง (Local)

```bash
# 1) เข้าโฟลเดอร์โปรเจกต์
cd news_gold

# 2) สร้าง virtual env (แนะนำ)
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3) ติดตั้ง library
pip install -r requirements.txt

# 4) ตั้งค่า secret
cp .env.example .env
#    แล้วเปิด .env ใส่ DISCORD_WEBHOOK_URL และ OPENAI_API_KEY ของจริง

# 5) รัน
python main.py
```

รอบแรกระบบจะ **seed** ข่าวปัจจุบันเงียบ ๆ (ไม่แจ้งย้อนหลัง) แล้วส่งข้อความ `🟢 ออนไลน์` เข้า Discord
จากนั้นจะแจ้งเฉพาะข่าว **ใหม่จริง ๆ** ที่ผ่านการกรอง

---

## 🔑 Environment Variables

| ตัวแปร | จำเป็น | ค่าเริ่มต้น | คำอธิบาย |
|--------|:---:|------|---------|
| `DISCORD_WEBHOOK_URL` | ✅ | — | URL webhook ของห้อง Discord |
| `OPENAI_API_KEY` | ✅ | — | API key จาก platform.openai.com |
| `OPENAI_MODEL` | — | `gpt-4o-mini` | โมเดล AI (ถูก+เร็ว) |
| `POLL_INTERVAL_SECONDS` | — | `60` | รอบดึงข่าว |
| `MAX_AGE_HOURS` | — | `6` | พิจารณาเฉพาะข่าวใหม่ภายในกี่ชั่วโมง |
| `MAX_ALERTS_PER_CYCLE` | — | `8` | เพดานแจ้งเตือนต่อรอบ (กัน flood) |
| `ALERT_MIN_IMPACT` | — | `Medium` | แจ้งเฉพาะ impact ระดับนี้ขึ้นไป (`Low`/`Medium`/`High`) — ตั้ง `High` ถ้าอยากให้เงียบสุด |
| `DEDUP_TITLE_HOURS` | — | `6` | กันข่าวเดียวกันจากหลายสำนักเด้งซ้ำ ภายในกี่ชั่วโมง |
| `DB_PATH` | — | `seen_news.db` | ที่อยู่ไฟล์ SQLite |

**สร้าง Discord Webhook:** ตั้งค่าเซิร์ฟเวอร์ → Integrations → Webhooks → New Webhook → Copy Webhook URL

---

## ☁️ Deploy 24/7

### ตัวเลือก A — Render (แนะนำ, เสถียร)
ใช้ **Background Worker** (ไม่ใช่ Web Service — เพราะ web service ฟรีจะ *sleep* เมื่อไม่มีคนเข้า ทำให้ลูปหยุด)

1. Push โปรเจกต์ขึ้น GitHub
2. Render → **New** → **Blueprint** → เลือก repo (จะอ่าน `render.yaml` ให้อัตโนมัติ)
3. ใส่ค่า `DISCORD_WEBHOOK_URL` และ `OPENAI_API_KEY` ในหน้า Environment
4. Deploy — เสร็จแล้วรันต่อเนื่องตลอด
   - `render.yaml` ผูก **persistent disk** ที่ `/data` ไว้แล้ว เพื่อให้ SQLite (ประวัติกันซ้ำ) ไม่หายตอน redeploy
   - Worker ไม่มี free tier (เริ่ม ~$7/เดือน) แต่แลกกับ "ไม่ sleep ตลอด 24 ชม."

### ตัวเลือก B — Railway (เริ่มง่าย มีเครดิตให้ลอง)
1. Railway → **New Project** → **Deploy from GitHub repo**
2. Railway อ่าน `Procfile` (`worker: python main.py`) อัตโนมัติ
3. แท็บ **Variables** ใส่ `DISCORD_WEBHOOK_URL`, `OPENAI_API_KEY`
4. (สำคัญ) เพิ่ม **Volume** mount ที่ `/data` แล้วตั้ง `DB_PATH=/data/seen_news.db`
   เพื่อให้ประวัติกันซ้ำอยู่รอดข้าม deploy

> ⚠️ **เรื่อง filesystem ชั่วคราว:** ทั้ง Render/Railway ถ้าไม่ผูก persistent disk ไฟล์ `.db` จะถูกล้างทุกครั้งที่ deploy ใหม่
> โค้ดรองรับเคสนี้แล้ว — เมื่อ DB ว่าง มันจะ **cold start seed** (จำข่าวปัจจุบันโดยไม่แจ้งย้อนหลัง) จึงไม่สแปม
> แต่แนะนำให้ผูก disk + ตั้ง `DB_PATH` เพื่อความต่อเนื่องของการกันซ้ำ

### ตัวเลือก C — VPS (แนะนำสุดสำหรับงานนี้ • ถูกที่สุด • SQLite อยู่รอดถาวร)

VPS เหมาะกับงานนี้ที่สุด เพราะ **ดิสก์เป็นของจริงถาวร** — ไฟล์ `seen_news.db` (ประวัติกันซ้ำ)
ไม่หายเหมือน Render/Railway และราคาถูกกว่า (VPS ~$4-5/เดือน เช่น DigitalOcean/Hetzner/Vultr/Linode)

รันด้วย **systemd** เพื่อให้สตาร์ตตอนบูต + รีสตาร์ตเองเมื่อ crash (ไฟล์ unit พร้อมใช้อยู่ใน `deploy/xauusd-news.service`)

```bash
# ===== บน VPS (Ubuntu/Debian) ในฐานะ root หรือ sudo =====

# 1) ติดตั้ง Python + git
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git

# 2) สร้าง user แยกสำหรับรันบอท (ปลอดภัยกว่ารันด้วย root)
sudo useradd -m -s /bin/bash botuser

# 3) วางโค้ดไว้ที่ /opt/news_gold  (clone จาก GitHub หรือ scp ขึ้นมา)
sudo git clone <your-repo-url> /opt/news_gold
#    หรืออัปจากเครื่องตัวเอง:  scp -r ./news_gold root@<VPS_IP>:/opt/news_gold
sudo chown -R botuser:botuser /opt/news_gold

# 4) สร้าง venv + ติดตั้ง library (รันในฐานะ botuser)
sudo -u botuser bash -c '
  cd /opt/news_gold &&
  python3 -m venv .venv &&
  .venv/bin/pip install --upgrade pip &&
  .venv/bin/pip install -r requirements.txt
'

# 5) ใส่ secret ลงไฟล์ .env
sudo -u botuser cp /opt/news_gold/.env.example /opt/news_gold/.env
sudo -u botuser nano /opt/news_gold/.env      # ใส่ DISCORD_WEBHOOK_URL + OPENAI_API_KEY

# 6) ติดตั้ง systemd service
sudo cp /opt/news_gold/deploy/xauusd-news.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now xauusd-news        # enable=สตาร์ตตอนบูต, now=เริ่มเดี๋ยวนี้

# 7) ตรวจสถานะ + ดู log แบบเรียลไทม์
systemctl status xauusd-news
journalctl -u xauusd-news -f
```

**คำสั่งที่ใช้บ่อย**

```bash
sudo systemctl restart xauusd-news     # รีสตาร์ต (เช่นหลังแก้ .env)
sudo systemctl stop xauusd-news        # หยุดชั่วคราว
journalctl -u xauusd-news --since "1 hour ago"   # ดู log ย้อนหลัง
```

**อัปเดตโค้ดใหม่**

```bash
cd /opt/news_gold && sudo -u botuser git pull
sudo -u botuser .venv/bin/pip install -r requirements.txt   # ถ้ามี lib เพิ่ม
sudo systemctl restart xauusd-news
```

> 📌 บน VPS ไม่ต้องตั้ง `DB_PATH` พิเศษ — ค่า default (`seen_news.db` ในโฟลเดอร์โปรเจกต์) อยู่บนดิสก์จริงถาวรอยู่แล้ว
> ดังนั้นประวัติกันซ้ำคงอยู่ข้ามการ restart/รีบูต ไม่ต้องผูก persistent disk เหมือน PaaS

### ตัวเลือก D — Windows VPS / Windows Server

Windows ไม่มี `systemd` — ใช้ **NSSM** (Non-Sucking Service Manager) ทำให้รันเป็น Windows Service
ที่สตาร์ตตอนบูต + รีสตาร์ตเองเมื่อ crash (เทียบเท่า systemd) สคริปต์ติดตั้งอยู่ใน `deploy/windows/`

```powershell
# ===== บน Windows VPS (CMD / PowerShell แบบ "Run as administrator") =====

# 1) ติดตั้ง Python 3 จาก https://www.python.org/downloads/windows/
#    *** ตอนติดตั้งให้ติ๊ก "Add python.exe to PATH" ***

# 2) วางโค้ดไว้ที่ C:\news_gold (clone หรือก๊อปขึ้นมา)
git clone <your-repo-url> C:\news_gold
cd C:\news_gold

# 3) สร้าง venv + ติดตั้ง library
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 4) ใส่ secret
copy .env.example .env
notepad .env            REM ใส่ DISCORD_WEBHOOK_URL + OPENAI_API_KEY

# 5) ทดสอบรันก่อน (ดับเบิลคลิก deploy\windows\run.bat หรือ)
.venv\Scripts\python main.py

# 6) ติดตั้ง NSSM: โหลด win64 จาก https://nssm.cc/download
#    แตกไฟล์ เอา nssm.exe ไปวางใน C:\Windows\System32

# 7) ติดตั้งเป็น service (คลิกขวา -> Run as administrator)
deploy\windows\install-service.bat
```

**คำสั่งจัดการ service**

```powershell
nssm status  XauusdNews          REM ดูสถานะ
nssm restart XauusdNews          REM รีสตาร์ต (หลังแก้ .env)
nssm stop    XauusdNews          REM หยุด
nssm edit    XauusdNews          REM เปิดหน้าต่างตั้งค่าแบบ GUI
nssm remove  XauusdNews confirm  REM ถอนการติดตั้ง
```

**ดู log:** service เขียน stdout/stderr ลงโฟลเดอร์ `logs\` → `type C:\news_gold\logs\out.log`

> 🔁 **ไม่อยากโหลด NSSM?** ใช้ **Task Scheduler** สร้าง task "At startup" ชี้
> Program = `C:\news_gold\.venv\Scripts\python.exe`, Arguments = `main.py`, Start in = `C:\news_gold`
> และแท็บ Settings ติ๊ก "If the task fails, restart every 1 minute" — แต่ NSSM คุม log/รีสตาร์ตง่ายกว่า

---

## 🛠️ การปรับแต่ง

- **เพิ่ม/ลดแหล่งข่าว:** แก้ลิสต์ `FEEDS` ใน `config.py`
- **ปรับ keyword:** แก้ลิสต์ `KEYWORDS` ใน `config.py`
- **ปรับตรรกะวิเคราะห์:** แก้ `SYSTEM_PROMPT` ใน `analyst.py`

## ❗ หมายเหตุเรื่องแหล่งข่าว (ทดสอบแล้ว ณ มิ.ย. 2026)

| แหล่ง | สถานะ | หมายเหตุ |
|-------|:---:|---------|
| ForexFactory Calendar (faireconomy XML) | ✅ | ปฏิทินข่าว ~75 events/สัปดาห์ — **rate limit แรง** จึง throttle ดึงทุก 10 นาที |
| Google News RSS (Gold / Fed / Geopolitics / Reuters) | ✅ | ฟรี เสถียรที่สุด ไม่ต้อง auth — เสาหลัก |
| FXStreet News | ✅ | ~30 ข่าว/รอบ |
| MarketWatch Top Stories | ✅ | ~10 ข่าว/รอบ |
| Investing.com Commodities | ✅ | ~10 ข่าว/รอบ (URL: `news_285.rss`) |

- **Reuters / Bloomberg** ปิด RSS สาธารณะฟรีไปแล้ว — โค้ดดึงเนื้อหาผ่าน **Google News RSS** แทน (เช่น `site:reuters.com`)
- **Kitco / DailyFX** บล็อก bot (404/403) จึงไม่ใส่ไว้
- feed ใดล่มชั่วคราว ระบบจะ `log` แล้วข้ามไป **ไม่ทำให้ทั้งระบบล่ม**
```
