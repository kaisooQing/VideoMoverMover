"""Auto cookies - Android stub.
On Android, we cannot launch headless browsers.
Cookie management must be done manually via file upload.
"""
import logging

logger = logging.getLogger(__name__)


def fetch_cookies_sync(url: str) -> dict:
    """Stub: auto cookie fetching is not available on Android."""
    logger.warning("Auto cookie fetching is not available on Android")
    return {'error': 'Auto cookie fetching is not available on Android. Please upload cookies manually.'}
