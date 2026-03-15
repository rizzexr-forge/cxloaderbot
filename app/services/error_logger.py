import json
import os
import logging
import asyncio
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

ERROR_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "errors.json")
MAX_LOG_ENTRIES = 200
_file_lock = threading.Lock()


async def log_error(user_id: int, platform: str, media_type: str, url: str, error_text: str):
    """Thread-safe error logging with rotation (keeps last MAX_LOG_ENTRIES)."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "platform": platform,
        "media_type": media_type,
        "url": url,
        "error": error_text
    }

    def _write_log():
        with _file_lock:
            logs = []
            if os.path.exists(ERROR_LOG_FILE):
                try:
                    with open(ERROR_LOG_FILE, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            logs = json.loads(content)
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Corrupted errors.json, starting fresh: %s", e)
                    logs = []

            logs.append(log_entry)

            # Rotate: keep only the last MAX_LOG_ENTRIES
            if len(logs) > MAX_LOG_ENTRIES:
                logs = logs[-MAX_LOG_ENTRIES:]

            try:
                with open(ERROR_LOG_FILE, "w", encoding="utf-8") as f:
                    json.dump(logs, f, ensure_ascii=False, indent=4)
            except OSError as e:
                logger.error("Failed to write error log: %s", e)

    await asyncio.to_thread(_write_log)
    logger.error("Download error [%s/%s] user=%s: %s", platform, media_type, user_id, error_text[:100])
