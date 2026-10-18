"""VYRO — v1 router aggregation."""
from fastapi import APIRouter

from app.api.v1 import (
    admin, auth, chats, comments, feed, frames, live, notifications, posts,
    search, users, wallet,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(posts.router)
api_router.include_router(comments.router)
api_router.include_router(comments.router_c)
api_router.include_router(feed.router)
api_router.include_router(chats.router)
api_router.include_router(wallet.router)
api_router.include_router(frames.router)
api_router.include_router(notifications.router)
api_router.include_router(search.router)
api_router.include_router(live.router)
api_router.include_router(admin.router)
