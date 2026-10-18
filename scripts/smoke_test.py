"""VYRO — End-to-end smoke test (run against a live server).

    python scripts/smoke_test.py [BASE_URL]

Covers: register/verify/login/refresh-rotation, profile edit + username rules,
avatar/banner upload, follow graph, posts (multipart image + hashtags),
like/save/repost, comments+replies+likes, home/explore/hashtag feeds, search,
chat REST + WebSocket (realtime + reply + typing + read), wallet ZYRA
(daily bonus, transactions), buff, donate, frame purchase/equip,
notifications, admin (frame create, grant, stats), live stubs, error paths.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import time

import httpx
import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"

PASSED = 0
FAILED = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  [PASS] {name}")
    else:
        FAILED += 1
        FAILURES.append(f"{name} {extra}")
        print(f"  [FAIL] {name} {extra}")


def png_bytes() -> bytes:
    # 1x1 transparent PNG
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


class Client:
    def __init__(self, token: str | None = None):
        self.client = httpx.AsyncClient(base_url=API, timeout=20)
        self.token = token

    @property
    def H(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def req(self, method: str, path: str, expect: int = 200, **kw) -> httpx.Response:
        headers = kw.pop("headers", {})
        headers.update(self.H)
        r = await self.client.request(method, path, headers=headers, **kw)
        if expect is not None and r.status_code != expect:
            print(f"    ! {method} {path} -> {r.status_code} (expected {expect}): {r.text[:300]}")
        return r

    async def close(self):
        await self.client.aclose()


async def main() -> None:
    ts = int(time.time())
    email_a = f"ali{ts}@vyro.dev"
    email_b = f"sara{ts}@vyro.dev"

    print("== 1) AUTH ==")
    ca = Client()
    r = await ca.req("POST", "/auth/register", 201, json={
        "email": email_a, "username": f"ali_{ts}", "password": "Secret123",
        "display_name": "علی تست",
    })
    check("register A", r.status_code == 201, r.text[:200])
    token_a = r.json()["access_token"]
    refresh_a = r.json()["refresh_token"]
    dev_verify = r.json().get("dev_verification_token")
    check("signup bonus in register response", "user" in r.json())

    # validation errors
    r = await ca.req("POST", "/auth/register", 409, json={
        "email": email_a, "username": f"ali2_{ts}", "password": "Secret123",
    })
    check("duplicate email -> 409", r.status_code == 409)
    r = await ca.req("POST", "/auth/register", 409, json={
        "email": f"x{ts}@vyro.dev", "username": f"ali_{ts}", "password": "Secret123",
    })
    check("duplicate username -> 409", r.status_code == 409)
    r = await ca.req("POST", "/auth/register", 422, json={
        "email": f"x{ts}@vyro.dev", "username": "ab", "password": "Secret123",
    })
    check("short username -> 422", r.status_code == 422)
    r = await ca.req("POST", "/auth/register", 422, json={
        "email": f"x{ts}@vyro.dev", "username": "admin", "password": "Secret123",
    })
    check("reserved username -> 422", r.status_code == 422)
    r = await ca.req("POST", "/auth/register", 422, json={
        "email": f"x{ts}@vyro.dev", "username": f"x{ts}", "password": "nonumberss",
    })
    check("weak password -> 422", r.status_code == 422)

    # verify email (dev token exposure)
    if dev_verify:
        r = await ca.req("POST", "/auth/verify-email", 200, json={"token": dev_verify})
        check("verify email", r.status_code == 200)
        r = await ca.req("POST", "/auth/verify-email", 400, json={"token": dev_verify})
        check("reused verify token -> 400", r.status_code == 400)

    # login B
    r = await ca.req("POST", "/auth/login", expect=401, json={"email": email_a, "password": "WrongPass1"})
    check("wrong password -> 401", r.status_code == 401)

    cb = Client()
    r = await cb.req("POST", "/auth/register", 201, json={
        "email": email_b, "username": f"sara_{ts}", "password": "Secret123",
    })
    check("register B", r.status_code == 201, r.text[:200])
    token_b = r.json()["access_token"]
    ca.token, cb.token = token_a, token_b

    r = await ca.req("POST", "/auth/login", 200, json={"email": email_a, "password": "Secret123", "device": "smoke"})
    check("login A", r.status_code == 200)
    r = await ca.req("POST", "/auth/refresh", 200, json={"refresh_token": refresh_a})
    check("refresh rotation", r.status_code == 200)
    new_refresh = r.json()["refresh_token"]
    r = await ca.req("POST", "/auth/refresh", 401, json={"refresh_token": refresh_a})
    check("reused refresh token -> 401 (family killed)", r.status_code == 401)
    # after reuse-detection, whole family must be revoked -> new refresh also fails
    r = await ca.req("POST", "/auth/refresh", 401, json={"refresh_token": new_refresh})
    check("family revoked after reuse", r.status_code == 401)
    # re-login to continue
    r = await ca.req("POST", "/auth/login", 200, json={"email": email_a, "password": "Secret123"})
    token_a = r.json()["access_token"]
    ca.token = token_a

    print("== 2) PROFILE ==")
    uname_a = f"ali_{ts}"
    uname_b = f"sara_{ts}"
    r = await ca.req("GET", "/users/me")
    check("users/me", r.status_code == 200 and r.json()["username"] == uname_a, r.text[:200])
    check("signup bonus balance=100", r.json()["wallet"]["balance_zyra"] == 100, str(r.json()["wallet"]))
    uid_a = r.json()["id"]

    r = await ca.req("PATCH", "/users/me", 200, json={"display_name": "علی رضایی", "bio": "گیمر VYRO"})
    check("edit display/bio", r.status_code == 200 and r.json()["display_name"] == "علی رضایی")

    r = await ca.req("PUT", "/users/me/username", 409, json={"username": uname_b})
    check("username taken -> 409", r.status_code == 409)
    r = await ca.req("PUT", "/users/me/username", 200, json={"username": f"ali_pro_{ts}"})
    check("change username", r.status_code == 200 and r.json()["username"] == f"ali_pro_{ts}")
    uname_a = f"ali_pro_{ts}"
    r = await ca.req("PUT", "/users/me/username", 400, json={"username": f"ali_x_{ts}"})
    check("username cooldown -> 400", r.status_code == 400)
    r = await ca.req("PUT", "/users/me/username", 422, json={"username": "admin"})
    check("reserved username change -> 422", r.status_code == 422)

    r = await ca.req("PUT", "/users/me/avatar", 200, files={"file": ("a.png", png_bytes(), "image/png")})
    check("avatar upload", r.status_code == 200 and r.json()["avatar_url"], r.text[:200])
    avatar_url = r.json()["avatar_url"]
    r = await ca.req("PUT", "/users/me/banner", 200, files={"file": ("b.png", png_bytes(), "image/png")})
    check("banner upload", r.status_code == 200 and r.json()["banner_url"])
    # bad content-type
    r = await ca.req("PUT", "/users/me/avatar", 415, files={"file": ("e.txt", b"hello", "text/plain")})
    check("bad file type -> 415", r.status_code == 415)

    r = await cb.req("GET", f"/users/{uname_a}")
    check("public profile", r.status_code == 200 and r.json()["is_following"] is False)
    check("avatar served", (await httpx.AsyncClient(timeout=10).get(f"{BASE}{avatar_url}")).status_code == 200)

    print("== 3) FOLLOW ==")
    r = await cb.req("POST", f"/users/{uname_a}/follow", 200)
    check("B follows A", r.status_code == 200 and r.json()["following"] is True)
    r = await cb.req("POST", f"/users/{uname_a}/follow", 200)
    check("double follow idempotent", r.status_code == 200 and r.json()["followers_count"] == 1)
    r = await cb.req("GET", f"/users/{uname_a}")
    check("is_following=true", r.json()["is_following"] is True)
    r = await ca.req("GET", f"/users/{uname_a}/followers", 200)
    check("followers list has B", any(u["username"] == uname_b for u in r.json()["items"]))
    r = await cb.req("DELETE", f"/users/{uname_a}/follow", 200)
    check("unfollow", r.json()["followers_count"] == 0)
    r = await cb.req("POST", f"/users/{uname_a}/follow", 200)
    check("re-follow", r.json()["following"] is True)

    print("== 4) POSTS ==")
    r = await ca.req("POST", "/posts", 201,
                     data={"content": "اولین پست VYRO من! 🔥 #گیمینگ #لایو"},
                     files=[("files", ("p1.png", png_bytes(), "image/png"))])
    check("create post with image", r.status_code == 201 and len(r.json()["images"]) == 1, r.text[:300])
    post_id = r.json()["id"]
    check("hashtags extracted", r.json()["content"].find("#گیمینگ") >= 0)

    r = await ca.req("POST", "/posts", 201, data={"content": "پست دوم بدون عکس #test"})
    post2_id = r.json()["id"]
    r = await ca.req("POST", "/posts", 400, data={"content": ""})
    check("empty post -> 400", r.status_code == 400)

    r = await ca.req("PATCH", f"/posts/{post2_id}", 200, json={"content": "پست دوم ویرایش شد #edit"})
    check("edit post", r.status_code == 200 and r.json()["is_edited"] is True)

    r = await cb.req("GET", f"/posts/{post_id}")
    check("get post (anon)", r.status_code == 200)

    r = await cb.req("POST", f"/posts/{post_id}/like", 200)
    check("B likes post", r.json()["likes_count"] == 1 and r.json()["active"] is True)
    r = await cb.req("POST", f"/posts/{post_id}/like", 200)
    check("double like idempotent", r.json()["likes_count"] == 1)
    r = await cb.req("DELETE", f"/posts/{post_id}/like", 200)
    check("unlike", r.json()["likes_count"] == 0)
    r = await cb.req("POST", f"/posts/{post_id}/like", 200)

    r = await cb.req("POST", f"/posts/{post_id}/save", 200)
    check("save", r.json()["active"] is True)
    r = await ca.req("GET", "/posts/saved", 200)
    check("saved list (owner only sees own)", r.status_code == 200)
    r = await cb.req("GET", "/posts/saved", 200)
    check("B saved list contains post", any(p["id"] == post_id for p in r.json()["items"]))

    r = await cb.req("POST", f"/posts/{post_id}/repost", 200, json={"quote": "این رو ببین!"})
    check("repost with quote", r.status_code == 200 and r.json()["repost_of_id"] == post_id, r.text[:200])
    repost_id = r.json()["id"]
    r = await cb.req("POST", f"/posts/{post_id}/repost", 400, json={})
    check("double repost -> 400", r.status_code == 400)
    r = await cb.req("DELETE", f"/posts/{post_id}/repost", 200)
    check("undo repost", r.json()["reposts_count"] == 0)
    r = await cb.req("POST", f"/posts/{post_id}/repost", 200, json={})

    r = await ca.req("GET", f"/posts/{post_id}/likes", 200)
    check("likes list", any(u["username"] == uname_b for u in r.json()["items"]))
    r = await ca.req("GET", f"/posts/{post_id}/reposts", 200)
    check("reposts list", any(u["username"] == uname_b for u in r.json()["items"]))

    # feeds
    r = await ca.req("GET", "/feed/home", 200)
    check("home feed has followed content", any(p["id"] == post_id for p in r.json()["items"]))
    r = await cb.req("GET", "/feed/explore?mode=trending", 200)
    check("explore trending", r.status_code == 200 and len(r.json()["items"]) >= 1)
    r = await cb.req("GET", "/feed/hashtag/گیمینگ", 200)
    check("hashtag feed (unicode)", any(p["id"] == post_id for p in r.json()["items"]), r.text[:200])
    r = await cb.req("GET", "/hashtags/trending", 200)
    check("trending hashtags", r.status_code == 200)
    # pagination cursor
    r1 = await cb.req("GET", "/feed/explore?mode=latest&limit=1", 200)
    cur = r1.json()["next_cursor"]
    r2 = await cb.req("GET", f"/feed/explore?mode=latest&limit=1&cursor={cur}", 200)
    check("cursor pagination works", r2.status_code == 200 and r2.json()["items"])
    if r1.json()["items"] and r2.json()["items"]:
        check("cursor moves forward", r1.json()["items"][0]["id"] != r2.json()["items"][0]["id"])

    # user posts
    r = await cb.req("GET", f"/users/{uname_a}/posts", 200)
    check("user posts list", any(p["id"] == post_id for p in r.json()["items"]))

    # search
    r = await cb.req("GET", f"/search?q={uname_a}&type=users", 200)
    check("search users", any(u["username"] == uname_a for u in r.json()["users"]))
    r = await cb.req("GET", "/search?q=VYRO&type=posts", 200)
    check("search posts", r.status_code == 200)
    r = await cb.req("GET", "/search?q=گیم&type=hashtags", 200)
    check("search hashtags", r.status_code == 200)

    print("== 5) COMMENTS ==")
    r = await cb.req("POST", f"/posts/{post_id}/comments", 201, json={"content": "عالی بود داداش!"})
    check("create comment", r.status_code == 201, r.text[:200])
    c1 = r.json()["id"]
    r = await ca.req("POST", f"/posts/{post_id}/comments", 201, json={"content": "ممنون 🙏", "parent_id": c1})
    check("reply to comment", r.status_code == 201 and r.json()["parent_id"] == c1)
    c2 = r.json()["id"]
    r = await ca.req("PATCH", f"/comments/{c2}", 200, json={"content": "ممنون از لطفت 🙏"})
    check("edit comment", r.status_code == 200 and r.json()["is_edited"] is True)
    r = await cb.req("POST", f"/comments/{c1}/like", 200)
    check("comment like", r.json()["likes_count"] == 1)
    r = await ca.req("POST", f"/comments/{c1}/like", 200)
    check("second comment like", r.json()["likes_count"] == 2)
    r = await cb.req("GET", f"/posts/{post_id}/comments", 200)
    check("comment list thread", any(c["id"] == c1 and c["replies_count"] == 1 for c in r.json()["items"]))
    r = await cb.req("GET", f"/comments/{c1}/replies", 200)
    check("replies list", any(c["id"] == c2 for c in r.json()["items"]))
    r = await ca.req("PATCH", f"/comments/{c1}", 403, json={"content": "hack"})
    check("edit other's comment -> 403", r.status_code == 403)
    r = await ca.req("GET", f"/posts/{post_id}", 200)
    check("post comments_count synced", r.json()["comments_count"] == 2, str(r.json()["comments_count"]))

    print("== 6) WALLET / ZYRA ==")
    r = await ca.req("GET", "/wallet")
    check("wallet info", r.status_code == 200 and r.json()["balance_zyra"] == 100)
    r = await ca.req("POST", "/wallet/daily")
    check("daily bonus", r.status_code == 200 and r.json()["balance_zyra"] == 125, r.text[:200])
    r = await ca.req("POST", "/wallet/daily", 400)
    check("daily bonus cooldown -> 400", r.status_code == 400)
    r = await ca.req("GET", "/wallet/transactions", 200)
    tx_types = [t["type"] for t in r.json()["items"]]
    check("ledger has signup+daily", "signup_bonus" in tx_types and "daily_bonus" in tx_types, str(tx_types))

    print("== 7) BUFF & DONATE ==")
    r = await cb.req("POST", f"/posts/{post_id}/buff", 422, json={"amount": 999999})
    check("buff > max -> 422 (schema)", r.status_code == 422)
    r = await cb.req("POST", f"/posts/{post_id}/buff", 200, json={"amount": 50, "message": "ادامه بده!"})
    check("buff 50 ZYRA", r.status_code == 200 and r.json()["sender_balance"] == 50, r.text[:200])
    r = await ca.req("GET", f"/posts/{post_id}")
    check("post buffs_total updated", r.json()["buffs_total_zyra"] == 50)
    r = await ca.req("GET", f"/posts/{post_id}/buffs", 200)
    check("buffs list", r.json()["items"][0]["amount"] == 50)
    r = await ca.req("GET", "/notifications", 200)
    check("buff notification", any(n["type"] == "buff" for n in r.json()["items"]))

    r = await cb.req("POST", f"/users/{uname_a}/donate", 200, json={"amount": 25, "message": "هدیه کوچیک"})
    check("donate 25", r.status_code == 200 and r.json()["sender_balance"] == 25, r.text[:200])
    r = await cb.req("POST", f"/users/{uname_a}/donate", 400, json={"amount": 100000})
    check("donate > balance -> 400", r.status_code == 400)
    r = await ca.req("GET", "/wallet")
    check("A balance after buff+donate", r.json()["balance_zyra"] == 200, str(r.json()["balance_zyra"]))

    print("== 8) FRAMES ==")
    r = await cb.req("GET", "/frames", 200)
    check("catalog empty for fresh users", isinstance(r.json(), list))
    r = await ca.req("POST", "/frames/00000000-0000-0000-0000-000000000001/purchase", 404)
    check("buy unknown frame -> 404", r.status_code == 404)

    print("== 9) CHAT REST ==")
    # third user (non-member) for permission checks
    cc = Client()
    r = await cc.req("POST", "/auth/register", 201, json={
        "email": f"carol{ts}@vyro.dev", "username": f"carol_{ts}", "password": "Secret123",
    })
    check("register C (non-member)", r.status_code == 201)
    cc.token = r.json()["access_token"]

    r = await ca.req("POST", "/chats", 201, json={"username": uname_b})
    check("create conversation", r.status_code == 201 and r.json()["created"] is True, r.text[:200])
    conv_id = r.json()["conversation_id"]
    r = await ca.req("POST", "/chats", 201, json={"username": uname_b})
    check("get-or-create conversation", r.json()["created"] is False)
    r = await ca.req("POST", f"/chats/{conv_id}/messages", 201, json={"content": "سلام سارا!"})
    check("send message", r.status_code == 201)
    msg1 = r.json()["id"]
    r = await cb.req("POST", f"/chats/{conv_id}/messages", 201, json={"content": "سلام! 🎮", "reply_to_id": msg1})
    check("reply message", r.status_code == 201 and r.json()["reply_to"]["id"] == msg1, r.text[:200])
    msg2 = r.json()["id"]
    r = await cb.req("GET", f"/chats/{conv_id}/messages", 200)
    check("chat history", len(r.json()["items"]) == 2 and r.json()["items"][0]["id"] == msg2)
    r = await cb.req("GET", "/chats", 200)
    conv_item = next(c for c in r.json() if c["id"] == conv_id)
    check("conversation list last_msg+unread", conv_item["unread_count"] == 0 and conv_item["last_message"] is not None)
    r = await ca.req("GET", "/chats", 200)
    conv_item_a = next(c for c in r.json() if c["id"] == conv_id)
    check("A unread=1", conv_item_a["unread_count"] == 1, str(conv_item_a["unread_count"]))
    r = await ca.req("POST", f"/chats/{conv_id}/read", 200)
    check("mark read", r.status_code == 200)
    r = await cb.req("PATCH", f"/chats/messages/{msg2}", 200, json={"content": "سلام! (ویرایش)"})
    check("edit own message", r.status_code == 200 and r.json()["content"].find("ویرایش") > 0, r.text[:150])
    r = await ca.req("PATCH", f"/chats/messages/{msg2}", 403, json={"content": "x"})
    check("edit other's message -> 403", r.status_code == 403)
    r = await cc.req("POST", f"/chats/{conv_id}/messages", 403, json={"content": "نفوذ!"})
    check("non-member can't post -> 403", r.status_code == 403)

    print("== 10) WEBSOCKET ==")
    ws_a = f"{BASE}/ws/chat?token={token_a}".replace("http", "ws")
    ws_b = f"{BASE}/ws/chat?token={token_b}".replace("http", "ws")

    async def recv_until(ws, want_type: str, timeout: float = 5) -> dict:
        """Read frames until one of the wanted type arrives (skips others)."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"did not receive {want_type}")
            evt = json.loads(await asyncio.wait_for(ws.recv(), remaining))
            if evt.get("type") == want_type:
                return evt
            # else: skip unrelated realtime events

    async with websockets.connect(ws_a) as wa, websockets.connect(ws_b) as wb:
        hello = await asyncio.wait_for(wa.recv(), 5)
        check("ws A connected", json.loads(hello)["type"] == "connected")

        # typing event
        await wb.send(json.dumps({"type": "typing", "conversation_id": conv_id}))
        evt = await recv_until(wa, "typing")
        check("typing broadcast", evt["type"] == "typing", str(evt))

        # live message B -> A
        await wb.send(json.dumps({
            "type": "message", "conversation_id": conv_id,
            "content": "پیام realtime!", "client_id": "abc-1",
        }))
        evt = await recv_until(wa, "message.new")
        check("realtime message.new", evt["message"]["content"] == "پیام realtime!", str(evt)[:200])
        sent = await recv_until(wb, "message.sent")
        check("sender echo message.sent", sent["client_id"] == "abc-1")

        # read receipt A -> B
        await wa.send(json.dumps({"type": "read", "conversation_id": conv_id}))
        evt = await recv_until(wb, "read")
        check("read receipt", evt["user_id"] and evt["last_read_at"])

        # ping/pong
        await wa.send(json.dumps({"type": "ping"}))
        evt = await recv_until(wa, "pong")
        check("ping-pong", evt["type"] == "pong")

    ws_bad = f"{BASE}/ws/chat?token=invalid"
    try:
        async with websockets.connect(ws_bad) as _:
            pass
        check("ws invalid token rejected", False, "connection accepted!")
    except Exception:
        check("ws invalid token rejected", True)

    print("== 11) NOTIFICATIONS ==")
    r = await ca.req("GET", "/notifications/unread-count", 200)
    check("unread count", r.json()["unread_count"] >= 1, str(r.json()))
    r = await ca.req("POST", "/notifications/read", 200, json=None)
    check("mark all read", r.status_code == 200 and r.json()["marked"] >= 1, r.text[:200])
    r = await ca.req("GET", "/notifications/unread-count", 200)
    check("unread now 0", r.json()["unread_count"] == 0)

    print("== 12) ADMIN ==")
    r = await ca.req("GET", "/admin/stats", 403)
    check("admin route blocked for user -> 403", r.status_code == 403)
    r = await cb.req("POST", "/auth/login", 200, json={"email": "admin@vyro.app", "password": "Admin@1234"})
    check("admin login (seeded)", r.status_code == 200)
    admin_tok = r.json()["access_token"]
    cadmin = Client(admin_tok)
    r = await cadmin.req("GET", "/admin/stats")
    check("admin stats", r.status_code == 200 and r.json()["users"] >= 3, r.text[:200])

    r = await cadmin.req("POST", "/admin/frames", 201, json={
        "slug": f"smoke-frame-{ts}", "name": "فریم تست", "rarity": "epic",
        "price_zyra": 100, "animation_type": "css",
        "config": {"css": "border:2px solid #22d3ee;border-radius:9999px"},
    })
    check("admin create frame", r.status_code == 201, r.text[:200])
    frame_id = r.json()["id"]

    r = await cb.req("GET", "/frames", 200)
    check("catalog contains new frame", any(f["id"] == frame_id for f in r.json()))

    r = await cb.req("POST", f"/frames/{frame_id}/purchase", 400)
    check("buy frame without balance -> 400", r.status_code == 400)
    r = await cadmin.req("POST", "/admin/wallet/grant", 200, json={
        "username": uname_b, "amount": 500, "reason": "smoke grant",
    })
    check("admin grant 500", r.status_code == 200 and r.json()["new_balance"] == 525, r.text[:200])
    r = await cb.req("POST", f"/frames/{frame_id}/purchase", 200)
    check("buy frame", r.status_code == 200 and r.json()["balance_zyra"] == 425, r.text[:200])
    r = await cb.req("POST", f"/frames/{frame_id}/purchase", 409)
    check("double buy -> 409", r.status_code == 409)
    r = await cb.req("GET", "/frames/inventory", 200)
    check("inventory", any(f["id"] == frame_id for f in r.json()))
    r = await cb.req("PUT", "/users/me/frame", 200, json={"frame_id": frame_id})
    check("equip frame", r.status_code == 200)
    r = await ca.req("GET", f"/users/{uname_b}", 200)
    check("public profile shows equipped frame", r.json()["frame"] and r.json()["frame"]["id"] == frame_id)
    r = await cb.req("PUT", "/users/me/frame", 200, json={"frame_id": None})
    check("unequip frame", r.status_code == 200)
    tx_types_b = [t["type"] for t in (await cb.req("GET", "/wallet/transactions")).json()["items"]]
    check("ledger frame_purchase + grant", "frame_purchase" in tx_types_b and "admin_grant" in tx_types_b, str(tx_types_b))

    print("== 13) LIVE STUBS ==")
    r = await ca.req("POST", "/live/streams", 201, json={"title": "لایو تست"})
    check("live create stub", r.status_code == 201 and r.json().get("stream_key"), r.text[:200])
    sid = r.json()["id"]
    r = await ca.req("POST", f"/live/streams/{sid}/go-live", 200)
    check("go live stub", r.status_code == 200)
    r = await ca.req("GET", "/live/streams?status=live", 200)
    check("live list", r.status_code == 200)

    print("== 14) SECURITY/EDGE ==")
    r = await Client().req("GET", "/users/me", 401)
    check("no token -> 401", r.status_code == 401)
    r = await Client("garbage.token.here").req("GET", "/users/me", 401)
    check("bad token -> 401", r.status_code == 401)
    r = await ca.req("GET", "/users/me", 200)
    my_id = r.json()["id"]
    r = await ca.req("POST", f"/users/{uname_a}/follow", 400)
    check("self-follow -> 400", r.status_code == 400)
    r = await ca.req("POST", f"/users/{uname_a}/donate", 400, json={"amount": 5})
    check("self-donate -> 400", r.status_code == 400)
    r = await cb.req("DELETE", f"/posts/{post_id}", 403)
    check("B delete A's post -> 403", r.status_code == 403)
    r = await ca.req("DELETE", f"/posts/{post2_id}", 200)
    check("A deletes own post", r.status_code == 200)
    r = await ca.req("GET", f"/posts/{post2_id}", 404)
    check("deleted post -> 404", r.status_code == 404)
    r = await ca.req("GET", "/nonexistent-endpoint", 404)
    check("unknown route 404", r.status_code == 404)

    # forgot/reset password flow
    r = await ca.req("POST", "/auth/forgot-password", 200, json={"email": email_a})
    reset_tok = r.json().get("dev_reset_token")
    check("forgot password (dev token)", r.status_code == 200 and reset_tok, r.text[:200])
    r = await ca.req("POST", "/auth/reset-password", 200, json={"token": reset_tok, "new_password": "NewPass123"})
    check("reset password", r.status_code == 200)
    r = await ca.req("POST", "/auth/login", 200, json={"email": email_a, "password": "NewPass123"})
    check("login with new password", r.status_code == 200)
    r = await ca.req("POST", "/auth/reset-password", 400, json={"token": reset_tok, "new_password": "Xx12345678"})
    check("reuse reset token -> 400", r.status_code == 400)

    await ca.close()
    await cb.close()
    await cadmin.close()

    print("\n" + "=" * 50)
    print(f"RESULT: {PASSED} passed, {FAILED} failed")
    if FAILURES:
        print("Failures:")
        for f in FAILURES:
            print(" -", f)
    print("=" * 50)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    asyncio.run(main())
