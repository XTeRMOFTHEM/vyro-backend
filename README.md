# VYRO Backend 🎮

**VYRO — Gaming-Social Platform Backend** · FastAPI · PostgreSQL · WebSocket

A complete, production-ready backend for a gaming-social platform (Omlet-Arcade style):
JWT auth with refresh-token rotation, profiles with animated frames, posts & nested
comments, realtime chat over WebSocket, a ZYRA token economy (append-only ledger),
notifications, search, admin panel — all async, cursor-paginated, rate-limited and
Dockerized. Full API map & WebSocket protocol documented below (in Persian).

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Tests](https://img.shields.io/badge/smoke%20test-133%2F133%20PASS-brightgreen?style=flat-square)](#-پوشش-تست-smoke_testpy--۱۳۳-چک)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

---

بک‌اند کامل و مقیاس‌پذیر پلتفرم گیمینگ‌سوشال **VYRO** (شبیه Omlet Arcade) با **FastAPI + PostgreSQL** — آماده اتصال به Flutter / Web.

---

## ✨ امکانات

| ماژول | توضیح |
|---|---|
| 🔐 **Auth** | ثبت‌نام با ایمیل + تایید ایمیل، ورود، JWT access کوتاه‌عمر + refresh token چرخشی (rotation) با تشخیص استفاده مجدد (token-theft)، فراموشی/بازیابی رمز، تغییر رمز، خروج تک‌دستگاه/همه‌دستگاه‌ها، rate-limit |
| 👤 **پروفایل** | username منحصربه‌فرد قابل تغییر (کول‌داون ۷ روزه)، نام نمایشی، بیو، **آواتار** و **بنر** (آپلود امن با magic-byte sniffing)، فریم انیمیشنی دور پروفایل |
| 🖼 **فریم‌ها** | فروشگاه فریم با ۴ نوع رندر (`css`, `image`, `video`, `lottie`)، rarity (common→legendary)، خرید با ZYRA، inventory، equip/unequip، **پنل ادمین برای افزودن فریم** (`POST /admin/frames`) |
| 🤝 **فالو** | follow/unfollow اتمیک، لیست followers/following با cursor، شمارنده‌های denormalized |
| 📝 **پست** | متن + تا ۴ عکس + هشتگ فارسی/انگلیسی، ویرایش (بازمحاسبه هشتگ)، حذف نرم، ریپست + کووت، لایک، سیو (بوکمارک)، **buff** |
| 💬 **کامنت** | کامنت تو در تو (reply)، لایک کامنت، ویرایش/حذف با چک دسترسی |
| 📰 **فید** | home (افراد دنبال‌شده + خودم)، explore (latest با keyset / trending با امتیاز تعامل)، هشتگ، ذخیره‌شده‌ها، صفحه‌بندی cursor-based (بدون OFFSET) |
| 💬 **چت** | DM یک‌به‌یک، پیام با **reply**، ویرایش/حذف پیام، read receipt، unread count، typing indicator، **WebSocket realtime** |
| 💎 **اقتصاد ZYRA** | کیف پول با **ledger append-only**، هدیه ثبت‌نام، پاداش روزانه، **buff روی پست** (هدیه جم به نویسنده)، **دونیت** به کاربر، خرید فریم — همه اتمیک با `SELECT FOR UPDATE` |
| 🔔 **نوتیفیکیشن** | فالو/لایک/کامنت/ریپلای/ریپست/buff/دونیت/خرید + **پوش زنده از طریق WebSocket** |
| 🔎 **جستجو** | کاربران / پست‌ها / هشتگ‌ها (آماده pg_trgm برای ILIKE سریع) |
| 📺 **لایو** | هسته placeholder (مدل + create/go-live/end + stream_key) برای اتصال RTMP/WebRTC در آینده |
| 🛡 **امنیت** | bcrypt(12)، policy رمز، نام‌های رزرو، anti-enumeration، rate-limit (Redis/حافظه)، media sniffing، error envelope یکسان |
| ⚙️ **عملیات** | Dockerfile + docker-compose (Postgres + Redis)، Alembic migrations، seed دمو، playground HTML، smoke test ۱۳۳ مرحله‌ای |

---

## 🚀 راه‌اندازی سریع

### راه ۱: Docker (پیشنهادی)
```bash
cd vyro-backend
docker compose up --build -d
# migrate + seed (بار اول):
docker compose exec app alembic upgrade head
docker compose exec app python scripts/seed.py
```
- API: http://localhost:8000/docs
- Playground: http://localhost:8000/playground

### راه ۲: دستی روی Linux / macOS
```bash
cd vyro-backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # DATABASE_URL را تنظیم کنید

alembic upgrade head        # ساخت جداول
python scripts/seed.py      # داده دمو + ادمین (اختیاری)

uvicorn app.main:app --reload
```

### راه ۳: ویندوز (Windows 10/11)

**پیش‌نیازها:**
1. **Python 3.11 یا بالاتر** — از [python.org/downloads](https://www.python.org/downloads/) نصب کنید. حین نصب حتماً تیک **"Add python.exe to PATH"** را بزنید.
2. **PostgreSQL 16** — دو حالت دارید:
   - **حالت ساده‌تر — فقط Docker برای دیتابیس:** اگر [Docker Desktop](https://www.docker.com/products/docker-desktop/) دارید، نیازی به نصب PostgreSQL نیست:
     ```powershell
     docker run -d --name vyro-db -e POSTGRES_USER=vyro -e POSTGRES_PASSWORD=vyro_secret -e POSTGRES_DB=vyro -p 5432:5432 postgres:16-alpine
     ```
   - **حالت بدون Docker:** PostgreSQL را از [postgresql.org/download/windows](https://www.postgresql.org/download/windows/) نصب کنید (رمز `postgres` را یادداشت کنید). سپس در **pgAdmin** یا **psql** دیتابیس و کاربر را بسازید:
     ```sql
     CREATE USER vyro WITH PASSWORD 'vyro_secret';
     CREATE DATABASE vyro OWNER vyro;
     ```
     مقدار پیش‌فرض `.env` دقیقاً همین است و نیازی به تغییر نیست.

**اجرا (دابل‌کلیک یا از CMD):**
```bat
cd vyro-backend
run.bat --seed
```
اسکریپت `run.bat` خودش همه کارها را انجام می‌دهد: ساخت venv ← نصب پکیج‌ها ← ساخت `.env` ← مایگریشن ← seed ← اجرای سرور.
- بار اول چند دقیقه طول می‌کشد (نصب پکیج‌ها)؛ دفعات بعد سریع است.
- بعد از پیام `Uvicorn running on http://0.0.0.0:8000` مرورگر را باز کنید: **http://127.0.0.1:8000/docs**

**اجرا به‌صورت دستی در PowerShell:**
```powershell
cd vyro-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
python scripts\seed.py
uvicorn app.main:app --reload
```
> اگر PowerShell خطای execution policy داد، اول این را اجرا کنید:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**تست خودکار در ویندوز:**
```bat
run.bat
```
در یک پنجره CMD دیگر داخل همان پوشه:
```bat
.venv\Scripts\python.exe scripts\smoke_test.py
```

> **نکته:** اگر Redis ندارید مشکلی نیست — پروژه به‌صورت خودکار از fallback حافظه‌ای استفاده می‌کند (برای تک‌سرور کاملاً کافی است).

### حساب‌های دمو (بعد از seed)
| نقش | ایمیل | رمز |
|---|---|---|
| ادمین | `admin@vyro.app` | `Admin@1234` |
| کاربر | `player1@vyro.dev` | `Player@123` |

### تست خودکار end-to-end
```bash
uvicorn app.main:app --port 8000 &   # سرور
python scripts/smoke_test.py         # ۱۳۳ چک از ثبت‌نام تا چت WS
```

---

## 🧱 ساختار پروژه

```
vyro-backend/
├── app/
│   ├── core/            # config, database(AsyncEngine), security(bcrypt/JWT), errors,
│   │                    # cache(Redis/memory), rate_limit, storage(magic-byte)
│   ├── models/          # SQLAlchemy 2.0: User, Profile, Post, Comment, Chat,
│   │                    # Wallet+Ledger, Frame, Follow, Notification, LiveStream
│   ├── schemas/         # Pydantic v2 + cursor pagination
│   ├── services/        # ✅ تمام منطق کسب‌وکار (auth, post, comment, chat,
│   │                    # wallet, frame, follow, notification, search, admin, live)
│   ├── api/v1/          # روترها: auth, users, posts, comments, feed, chats,
│   │                    # wallet, frames, notifications, search, live, admin
│   ├── ws/              # ConnectionManager + endpoint /ws/chat
│   ├── static/          # playground.html (ابزار تست دستی)
│   └── main.py          # فکتوری اپ: CORS, gzip, rate-limit, error envelope
├── alembic/             # مایگریشن‌ها (+ trigram index برای سرچ)
├── scripts/             # seed.py + smoke_test.py
├── docker-compose.yml   # app + postgres + redis
└── requirements.txt
```

---

## 📡 API — نقشه کامل

پیشوند همه: `/api/v1` — مستندات تعاملی: `/docs` (Swagger) و `/redoc`

### Auth
| متد | مسیر | توضیح |
|---|---|---|
| POST | `/auth/register` | ثبت‌نام → توکن + (dev) توکن تایید ایمیل |
| POST | `/auth/login` | ورود |
| POST | `/auth/refresh` | چرخش refresh token (کشف reuse → ابطال خانواده) |
| POST | `/auth/logout` · `/auth/logout-all` | خروج |
| POST | `/auth/verify-email` · `/auth/resend-verification` | تایید ایمیل |
| POST | `/auth/forgot-password` · `/auth/reset-password` | بازیابی رمز |
| POST | `/auth/change-password` | تغییر رمز |

### کاربران و فالو
`GET /users/me` · `PATCH /users/me` · `PUT /users/me/username` · `PUT /users/me/avatar` · `PUT /users/me/banner` · `PUT /users/me/frame` · `GET /users/{username}` · `GET /users/{username}/posts` · `GET /users/{username}/followers|following` · `POST|DELETE /users/{username}/follow` · `POST /users/{username}/donate`

### پست‌ها
`POST /posts` (multipart: content + files + image_urls) · `GET|PATCH|DELETE /posts/{id}` · `POST|DELETE /posts/{id}/like` · `POST|DELETE /posts/{id}/save` · `POST|DELETE /posts/{id}/repost` · `GET /posts/{id}/likes|reposts|buffs` · `POST /posts/{id}/buff` · `GET /posts/saved`

### کامنت‌ها
`POST|GET /posts/{post_id}/comments` · `GET /comments/{id}/replies` · `PATCH|DELETE /comments/{id}` · `POST|DELETE /comments/{id}/like`

### فید و هشتگ
`GET /feed/home` · `GET /feed/explore?mode=latest|trending` · `GET /feed/hashtag/{tag}` · `GET /hashtags/trending`

### چت
`GET /chats` · `POST /chats` · `GET|POST /chats/{id}/messages` · `POST /chats/{id}/read` · `PATCH|DELETE /chats/messages/{id}` · **WS `/ws/chat?token=`**

### کیف پول و فریم
`GET /wallet` · `GET /wallet/transactions` · `POST /wallet/daily` · `GET /frames` · `GET /frames/inventory` · `POST /frames/{id}/purchase`

### دیگر
`GET|POST /notifications` · `GET /notifications/unread-count` · `POST /notifications/read` · `GET /search?q=&type=` · `GET /health` · `GET /api/v1/meta`

### ادمین (role=admin)
`GET /admin/stats` · `GET /admin/users` · `POST /admin/users/{id}/activate|deactivate|role` · `POST /admin/wallet/grant` · `POST|PATCH /admin/frames`

### لایو (BETA — placeholder)
`GET|POST /live/streams` · `GET /live/streams/{id}` · `POST /live/streams/{id}/go-live|end`

---

## 🔌 پروتکل WebSocket چت

```
اتصال:  ws://host/ws/chat?token=<ACCESS_TOKEN>

کلاینت ← سرور:
{"type":"message","conversation_id":"...","content":"...","reply_to_id":null,"client_id":"c1"}
{"type":"typing","conversation_id":"..."}
{"type":"read","conversation_id":"..."}
{"type":"ping"}

سرور ← کلاینت:
{"type":"message.new","message":{...}}                  # به همه اعضا (شامل دستگاه‌های فرستنده)
{"type":"message.sent","client_id":"c1","message":{...}} # echo با client_id
{"type":"typing","conversation_id":"...","user_id":"..."}
{"type":"read","conversation_id":"...","user_id":"...","last_read_at":"..."}
{"type":"message.edited" | "message.deleted","message":{...}}
{"type":"notification","notification":{...}}            # پوش زنده نوتیفیکیشن
```

---

## 🖼 قرارداد فریم انیمیشنی (برای پنل ادمین)

فریم با JSONB آزاد ذخیره می‌شود تا بدون migration بتوانید نوع جدید اضافه کنید:

```json
{
  "slug": "gold-vip",
  "name": "طلایی VIP",
  "rarity": "legendary",          // common | rare | epic | legendary
  "price_zyra": 1000,
  "animation_type": "css",        // css | image | video | lottie
  "asset_url": null,              // برای image/video/lottie
  "config": {
    "css": "border: 4px solid transparent; border-radius:9999px; background: linear-gradient(60deg,#fde047,#f59e0b) border-box;",
    "keyframes": "0%,100%{box-shadow:0 0 10px #fbbf24}50%{box-shadow:0 0 26px #fbbf24}",
    "duration": "2.4s"
  }
}
```
افزودن از طریق `POST /api/v1/admin/frames` — فریم فوراً در کاتالوگ (با کش ۵ دقیقه‌ای) ظاهر می‌شود.

## 💎 اقتصاد ZYRA

- هدیه ثبت‌نام: **100 ZYRA** · پاداش روزانه: **25 ZYRA** (هر ۲۴ ساعت)
- Buff پست: `POST /posts/{id}/buff` — مبلغ ۱ تا ۱۰,۰۰۰، کسر از فرستنده، واریز به نویسنده + ثبت در هر دو ledger
- دونیت: `POST /users/{username}/donate`
- خرید فریم: `POST /frames/{id}/purchase` — چک موجودی + inventory + ledger
- همه تراکنش‌های مالی با `SELECT ... FOR UPDATE` به‌ترتیب user_id قفل می‌شوند (بدون deadlock) و در جدول `transactions` فقط-append ثبت می‌شوند.

---

## 📈 مقیاس‌پذیری — تصمیم‌های معماری

- **ASGI + asyncpg pool** (pool_size=20 + overflow، pre-ping، statement timeout)
- **Keyset pagination** همه‌جا — بدون OFFSET decay
- **شمارنده‌های denormalized** با UPDATE اتمیک (نه read-modify-write)
- **کش پلاگینی**: Redis یا حافظه درون‌پردازشی (`REDIS_URL`) — کاتالوگ فریم، ترندها، membership گفتگو
- **Rate-limit پلاگینی** با همان بک‌اند
- **WS manager مستقل** → برای چند سرور فقط با Redis pub/sub جایگزین fan-out کنید (ایترفیس ثابت)
- ایندکس‌های ترکیبی روی مسیرهای داغ (post/created_at، conv/created_at، notif/recipient...)
- pg_trgm برای search سریع (در migration در صورت موجود بودن)
- Media: LocalStorage با قرارداد URL ثابت → جایگزینی با S3 فقط با تغییر `app/core/storage.py`
- Feed v1 با SQL join؛ برای مقیاس خیلی بالا fan-out به Redis/Celery (نقطه اتصال در `post_service.home_feed`)

## 🧭 نقشه راه پیشنهادی
1. اتصال UI (Flutter/Web) — همه پاسخ‌ها JSON ساده و CORS باز
2. پنل ادمین فریم‌ها — endpointها آماده‌اند
3. لایو استریم — مدل و lifecycle آماده؛ کافیست ingest (RTMP مثل SRS/nginx-rtmp) و viewer count به `live_service` وصل شود
4. نوتیفیکیشن پوش (FCM) و ایمیل واقعی (SMTP در `.env`)
5. گزارش‌دهی/مودریشن محتوا

---

## 🧪 پوشش تست (smoke_test.py — ۱۳۳ چک)
ثبت‌نام/اعتبارسنجی‌ها/تایید ایمیل → پروفایل (username cooldown، آپلودها) → فالو → پست/هشتگ/لایک/سیو/ریپست/فیدها/cursor → کامنت تو در تو → کیف پول/pاداش روزانه/ledger → buff/دونیت → فریم (خرید/inventory/equip) → چت REST → **WebSocket realtime** → نوتیفیکیشن → ادمین → لایو → موارد امنیتی (401/403/422، reuse refresh، self-follow…)
