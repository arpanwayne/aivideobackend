"""
Public storage helper.

Vercel's Python serverless functions run on a read-only filesystem except for
/tmp, and /tmp itself is wiped between invocations and can't be served back
to a browser (there's no "http://127.0.0.1:8000/static/..." in production —
that's not even the right host). So anything we generate locally — a
composited image, an FFmpeg-rendered video — has to be uploaded to real
external storage before we can return a URL that actually works.

We reuse the fal.ai storage that's already required for image/video
generation (FAL_API_KEY) rather than standing up a second storage provider.
"""
import asyncio
import logging
import os

from app.core.config import settings

logger = logging.getLogger(__name__)


async def upload_public(path) -> str | None:
    """Upload a local file to fal.ai storage and return its public URL.

    Returns None (never raises) if FAL_API_KEY isn't set or the upload fails,
    so callers can fall back to something sensible instead of handing back a
    broken localhost URL.
    """
    if not settings.FAL_API_KEY:
        logger.warning("FAL_API_KEY not set — cannot upload to public storage")
        return None

    try:
        import fal_client
        os.environ["FAL_KEY"] = settings.FAL_API_KEY

        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(None, lambda: fal_client.upload_file(str(path)))
        return url
    except Exception as e:
        logger.error(f"Failed to upload {path} to public storage: {e}")
        return None
