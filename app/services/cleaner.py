import os
import asyncio
import logging

logger = logging.getLogger(__name__)


async def cleanup_file(filepath: str, delay: int = 0):
    """Wait for delay seconds and then delete the file."""
    if delay > 0:
        await asyncio.sleep(delay)

    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.debug("Cleaned up: %s", filepath)
    except OSError as e:
        logger.warning("Failed to delete %s: %s", filepath, e)
