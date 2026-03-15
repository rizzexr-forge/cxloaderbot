import os
import json
import time
import logging

logger = logging.getLogger(__name__)

LIMITS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "limits.json")

DEFAULT_LIMITS = {
    "MAX_TIKTOK_PHOTOS": 35,
    "MAX_VIDEO_DURATION_SEC": 3600,
    "MAX_VIDEO_SIZE_MB": 500
}

_cache = {"data": None, "mtime": 0}


def load_limits() -> dict:
    """Load limits with file-modification-time caching — only re-reads when file changes."""
    try:
        current_mtime = os.path.getmtime(LIMITS_FILE) if os.path.exists(LIMITS_FILE) else 0
    except OSError:
        current_mtime = 0

    if _cache["data"] is not None and current_mtime == _cache["mtime"]:
        return _cache["data"]

    if not os.path.exists(LIMITS_FILE):
        try:
            with open(LIMITS_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_LIMITS, f, indent=4)
        except OSError as e:
            logger.warning("Cannot create limits.json: %s", e)
        _cache["data"] = DEFAULT_LIMITS.copy()
        _cache["mtime"] = 0
        return _cache["data"]

    try:
        with open(LIMITS_FILE, 'r', encoding='utf-8') as f:
            limits = json.load(f)

        updated = False
        for k, v in DEFAULT_LIMITS.items():
            if k not in limits:
                limits[k] = v
                updated = True

        if updated:
            with open(LIMITS_FILE, 'w', encoding='utf-8') as f:
                json.dump(limits, f, indent=4)

        _cache["data"] = limits
        _cache["mtime"] = current_mtime
        return limits
    except Exception as e:
        logger.warning("Error reading limits.json: %s", e)
        _cache["data"] = DEFAULT_LIMITS.copy()
        return _cache["data"]
