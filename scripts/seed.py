"""VYRO — Seed demo data.

    python scripts/seed.py

Creates: admin, 6 demo users, 6 animated frames (CSS-based, render anywhere),
posts with hashtags, follows, likes, a buff, a DM conversation, notifications.
Idempotent: skips if admin already exists.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Buff, Comment, Conversation, ConversationParticipant, Follow, Frame, Message,
    Notification, Post, Profile, User, Wallet,
)
from app.models.base import utcnow  # noqa: E402
from app.models.wallet import TX_SIGNUP_BONUS  # noqa: E402
from sqlalchemy import select  # noqa: E402

FRAMES = [
    {
        "slug": "neon-purple", "name": "نئون بنفش", "rarity": "common", "price_zyra": 50,
        "description": "گرمای نئون بنفش دور پروفایل",
        "animation_type": "css",
        "config": {
            "css": "border: 3px solid transparent; border-radius: 9999px; background: linear-gradient(45deg,#a855f7,#ec4899,#a855f7) border-box;",
            "keyframes": "0%{filter:hue-rotate(0deg)}100%{filter:hue-rotate(360deg)}",
            "duration": "4s",
        },
    },
    {
        "slug": "fire-flame", "name": "شعله‌های آتش", "rarity": "rare", "price_zyra": 150,
        "description": "شعله‌های زنده دور آواتار",
        "animation_type": "css",
        "config": {
            "css": "border: 3px solid transparent; border-radius: 9999px; background: linear-gradient(45deg,#f97316,#ef4444,#fbbf24) border-box; box-shadow: 0 0 12px #f97316aa;",
            "keyframes": "0%,100%{box-shadow:0 0 8px #f97316aa}50%{box-shadow:0 0 20px #ef4444cc}",
            "duration": "1.6s",
        },
    },
    {
        "slug": "galaxy", "name": "کهکشان", "rarity": "epic", "price_zyra": 400,
        "description": "چرخش کهکشانی بنفش-آبی",
        "animation_type": "css",
        "config": {
            "css": "border: 3px solid transparent; border-radius: 9999px; background: conic-gradient(from 0deg,#6366f1,#a855f7,#22d3ee,#6366f1) border-box;",
            "keyframes": "0%{transform:rotate(0)}100%{transform:rotate(360deg)}",
            "duration": "6s",
        },
    },
    {
        "slug": "gold-vip", "name": "طلایی VIP", "rarity": "legendary", "price_zyra": 1000,
        "description": "درخشش طلایی مخصوص VIP ها",
        "animation_type": "css",
        "config": {
            "css": "border: 4px solid transparent; border-radius: 9999px; background: linear-gradient(60deg,#fde047,#f59e0b,#fff7ae,#f59e0b) border-box; box-shadow:0 0 18px #fbbf24aa;",
            "keyframes": "0%,100%{box-shadow:0 0 10px #fbbf2488}50%{box-shadow:0 0 26px #fbbf24dd}",
            "duration": "2.4s",
        },
    },
    {
        "slug": "digital-rain", "name": "باران دیجیتال", "rarity": "rare", "price_zyra": 120,
        "description": "استایل ماتریکسی سبز نئونی",
        "animation_type": "css",
        "config": {
            "css": "border: 3px solid transparent; border-radius: 9999px; background: linear-gradient(180deg,#22c55e,#065f46,#22c55e) border-box;",
            "keyframes": "0%{opacity:.7}50%{opacity:1}100%{opacity:.7}",
            "duration": "2s",
        },
    },
    {
        "slug": "heartbeat", "name": "قلب تپنده", "rarity": "common", "price_zyra": 80,
        "description": "ضربان قلب صورتی دور پروفایل",
        "animation_type": "css",
        "config": {
            "css": "border: 3px solid #f472b6; border-radius: 9999px;",
            "keyframes": "0%,100%{transform:scale(1)}14%{transform:scale(1.06)}28%{transform:scale(1)}42%{transform:scale(1.06)}70%{transform:scale(1)}",
            "duration": "1.8s",
        },
    },
]

USERS = [
    ("taha_gamer", "تاها گیمر", "player1@vyro.dev", "Player@123", "گیمر حرفه‌ای موبایل | PUBG & CoD"),
    ("sara_sniper", "سارا اسنایپر", "player2@vyro.dev", "Player@123", "اسنایپر COD Mobile 👑"),
    ("ali_reza", "علی رضا", "player3@vyro.dev", "Player@123", "استریمر گیمینگ و منتقد بازی‌ها"),
    ("nazanin_x", "نازنین", "player4@vyro.dev", "Player@123", "_content creator | کلش و براوال"),
    ("mehrdad_pro", "مهرداد پرو", "player5@vyro.dev", "Player@123", "کوچ Free Fire — روزی ۲ ساعت لایو"),
    ("shirin_play", "شیرین پلی", "player6@vyro.dev", "Player@123", "لول ۳۰ کلش رویال 🎮"),
]

POSTS = [
    ("taha_gamer", "امشب ساعت ۹ لایو پابجی می‌ذارم، رنک پوش تا کانکوئرور! 🎮 #پابجی #لایو #گیمینگ", 32, 12),
    ("sara_sniper", "بهترین تنظیمات حساسیت COD Mobile رو ریختم تو پیج، امتحان کنید #کالموبایل #حساسیت", 27, 9),
    ("ali_reza", "بررسی کامل صحنه‌های جدید آپدیت Free Fire — کدوم کاراکتر رو می‌گیرید؟ #فری_فایر #بررسی", 19, 6),
    ("nazanin_x", "برووال استارز تا ۱۵ هزار تروفی رسید! لول بالاخره ۱۴ شد 🏆 #برووال_استارز #تروفی", 41, 15),
    ("mehrdad_pro", "ترفند هایدن پورت مپ برمودا؛ جای امن برای لووت سریع #فری_فایر #ترفند", 23, 7),
    ("shirin_play", "کلن جدید زدیم، اسمش Stars of VYRO هست. برای وار هر شب آنلاینیم ⚔️ #کلش_رویال #وار", 35, 11),
    ("taha_gamer", "چیلنچ امروز: با شاتگان سه کیل در یک مسابقه — کلیپش رو ببینید! #پابجی #چالش", 18, 5),
    ("sara_sniper", "استریم فردا با مخاطب خاص، سوالاتون رو کامنت کنید 💬 #لایو #پرسش", 12, 4),
]


async def main() -> None:
    async with SessionLocal() as db:
        admin = (
            await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
        ).scalar_one_or_none()
        if admin:
            print("[seed] already seeded — skipping")
            return

        # ---- admin ----
        admin = User(
            email=settings.ADMIN_EMAIL,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            role="admin",
            is_verified=True,
        )
        db.add(admin)
        await db.flush()
        db.add(Profile(user_id=admin.id, username=settings.ADMIN_USERNAME, display_name="VYRO Admin", bio="مدیر پلتفرم VYRO"))
        db.add(Wallet(user_id=admin.id, balance=100000, total_earned=100000))

        # ---- users ----
        profiles: dict[str, Profile] = {}
        for username, dn, email, pwd, bio in USERS:
            u = User(email=email, password_hash=hash_password(pwd), is_verified=True)
            db.add(u)
            await db.flush()
            p = Profile(user_id=u.id, username=username, display_name=dn, bio=bio)
            db.add(p)
            db.add(Wallet(user_id=u.id, balance=500, total_earned=600, total_spent=100))
            profiles[username] = p
        await db.flush()

        # ---- frames ----
        frame_rows = []
        for f in FRAMES:
            frame = Frame(**f)
            db.add(frame)
            frame_rows.append(frame)
        await db.flush()

        # give a couple of users owned frames + equip
        from app.models import UserFrame

        db.add(UserFrame(user_id=profiles["taha_gamer"].user_id, frame_id=frame_rows[0].id, source="purchase"))
        db.add(UserFrame(user_id=profiles["nazanin_x"].user_id, frame_id=frame_rows[3].id, source="purchase"))
        profiles["taha_gamer"].equipped_frame_id = frame_rows[0].id
        profiles["nazanin_x"].equipped_frame_id = frame_rows[3].id

        # ---- follows (graph) ----
        pairs = [
            ("taha_gamer", "sara_sniper"), ("taha_gamer", "nazanin_x"),
            ("sara_sniper", "taha_gamer"), ("sara_sniper", "ali_reza"),
            ("ali_reza", "taha_gamer"), ("nazanin_x", "shirin_play"),
            ("mehrdad_pro", "taha_gamer"), ("shirin_play", "nazanin_x"),
            ("shirin_play", "mehrdad_pro"), ("nazanin_x", "taha_gamer"),
        ]
        for a, b in pairs:
            db.add(Follow(follower_id=profiles[a].user_id, following_id=profiles[b].user_id))
            profiles[b].followers_count += 1
            profiles[a].following_count += 1

        # ---- posts + hashtags ----
        import re

        HASHTAG_RE = re.compile(r"#([\w\u0600-\u06FF]{2,30})", re.UNICODE)
        posts: list[Post] = []
        for username, content, likes, comments_n in POSTS:
            p = Post(author_id=profiles[username].user_id, content=content, images=[])
            db.add(p)
            await db.flush()
            posts.append(p)
            profiles[username].posts_count += 1
            tags = {m.group(1).lower() for m in HASHTAG_RE.finditer(content)}
            for tag in tags:
                h = (
                    await db.execute(select(Frame).limit(0))  # placeholder, replaced below
                )
                from app.models import Hashtag

                h = (await db.execute(select(Hashtag).where(Hashtag.name == tag))).scalar_one_or_none()
                if not h:
                    h = Hashtag(name=tag, posts_count=0)
                    db.add(h)
                    await db.flush()
                h.posts_count += 1
                from app.models import PostHashtag

                db.add(PostHashtag(post_id=p.id, hashtag_id=h.id))
            # synthetic likes
            from app.models import Like

            likers = [pr for un, pr in profiles.items() if un != username][:likes % 6]
            for pr in likers:
                db.add(Like(user_id=pr.user_id, post_id=p.id))
            p.likes_count = likes

        # comments on first two posts
        db.add(Comment(post_id=posts[0].id, author_id=profiles["sara_sniper"].user_id, content="من هستم امشب! 🔥"))
        db.add(Comment(post_id=posts[0].id, author_id=profiles["ali_reza"].user_id, content="رنک پوش موفق باشی داداش"))
        db.add(Comment(post_id=posts[1].id, author_id=profiles["taha_gamer"].user_id, content="حساسیتش عالی بود، ممنون!"))
        posts[0].comments_count = 2
        posts[1].comments_count = 1

        # ---- a buff on post 1 ----
        buff = Buff(
            sender_id=profiles["nazanin_x"].user_id,
            post_id=posts[0].id,
            amount=50,
            message="لایوت عالی بود، اینم جم! 💎",
        )
        db.add(buff)
        posts[0].buffs_total_zyra = 50
        posts[0].buffs_count = 1

        # ---- conversation between taha & sara ----
        conv = Conversation()
        db.add(conv)
        await db.flush()
        db.add(ConversationParticipant(conversation_id=conv.id, user_id=profiles["taha_gamer"].user_id))
        db.add(ConversationParticipant(conversation_id=conv.id, user_id=profiles["sara_sniper"].user_id))
        m1 = Message(conversation_id=conv.id, sender_id=profiles["taha_gamer"].user_id, content="سلام سارا! تیم دو نفره می‌بندی امشب؟")
        await db.flush()
        conv.last_message_at = m1.created_at
        conv.last_message_preview = m1.content[:200]
        db.add(m1)
        db.add(Message(conversation_id=conv.id, sender_id=profiles["sara_sniper"].user_id, content="حتما! ساعت ۹ آنلاینم 🎯"))

        # ---- notifications ----
        db.add(Notification(recipient_id=profiles["taha_gamer"].user_id, actor_id=profiles["sara_sniper"].user_id, type="follow", ref_type="user", ref_id=profiles["sara_sniper"].user_id))
        db.add(Notification(recipient_id=profiles["taha_gamer"].user_id, actor_id=profiles["nazanin_x"].user_id, type="buff", ref_type="post", ref_id=posts[0].id, data={"amount": 50}))

        await db.commit()
        print("[seed] done — admin:", settings.ADMIN_EMAIL, "/", settings.ADMIN_PASSWORD)
        print("[seed] demo login: player1@vyro.dev / Player@123")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
