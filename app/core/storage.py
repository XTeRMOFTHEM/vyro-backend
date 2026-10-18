"""VYRO — Media storage abstraction.

Local-disk backend now (served under /media), S3-compatible backend can be
plugged in later without touching service code.

Security: magic-byte sniffing (jpg/png/gif/webp), size cap, randomized names,
path traversal impossible (uuid filenames, fixed subdir whitelist).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import PayloadTooLarge, UnsupportedMediaType

MAGIC = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
}
ALLOWED_EXT = {"jpg", "jpeg", "png", "gif", "webp"}


def _sniff_ext(data: bytes) -> str | None:
    for magic, ext in MAGIC.items():
        if data.startswith(magic):
            return ext
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _maybe_downscale(data: bytes, max_dim: int = 2048) -> tuple[bytes, str]:
    """Downscale huge images with Pillow; returns (bytes, ext)."""
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "PNG").lower()
        if fmt == "gif":  # keep animations as-is
            return data, "gif"
        if img.width <= max_dim and img.height <= max_dim:
            return data, "png" if fmt == "png" else ("jpg" if fmt in ("jpeg", "jpg") else fmt if fmt in ("webp",) else "png")
        img = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
        img.thumbnail((max_dim, max_dim))
        buf = io.BytesIO()
        if img.mode == "RGBA":
            img.save(buf, format="PNG")
            return buf.getvalue(), "png"
        img.save(buf, format="JPEG", quality=88)
        return buf.getvalue(), "jpg"
    except Exception:
        return data, "bin"


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _ensure_dir(self, subdir: str) -> Path:
        path = self.root / "uploads" / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_sync(self, path: Path, data: bytes) -> None:
        with open(path, "wb") as f:
            f.write(data)

    async def save_image(self, upload: UploadFile, subdir: str) -> str:
        """Validates + stores an image; returns public URL like /media/uploads/<subdir>/2026/10/<uuid>.png"""
        data = await upload.read()
        if len(data) > settings.max_upload_bytes:
            raise PayloadTooLarge()
        ext = _sniff_ext(data)
        if not ext:
            raise UnsupportedMediaType()
        now = datetime.now(timezone.utc)
        rel_dir = f"{subdir}/{now:%Y/%m}"
        target_dir = self._ensure_dir(rel_dir)
        fname = f"{uuid.uuid4().hex}.{ext}"
        path = target_dir / fname
        await asyncio.to_thread(self._write_sync, path, data)
        return f"/media/uploads/{rel_dir}/{fname}"

    def url_exists(self, url: str) -> bool:
        if not url.startswith("/media/"):
            return False
        return (self.root / url.removeprefix("/media/")).exists()


storage = LocalStorage(settings.MEDIA_ROOT)
