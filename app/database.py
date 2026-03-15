import aiosqlite
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'users_data.sqlite')

# Reusable connection holder — avoids opening/closing on every query
_db_conn: aiosqlite.Connection | None = None


async def _get_db() -> aiosqlite.Connection:
    """Get or create a persistent database connection."""
    global _db_conn
    if _db_conn is None:
        _db_conn = await aiosqlite.connect(DB_PATH)
        _db_conn.row_factory = aiosqlite.Row
        await _db_conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent perf
        await _db_conn.execute("PRAGMA busy_timeout=5000")
        logger.info("Database connection established: %s", DB_PATH)
    return _db_conn


async def close_db():
    """Close the persistent database connection."""
    global _db_conn
    if _db_conn is not None:
        await _db_conn.close()
        _db_conn = None
        logger.info("Database connection closed")


async def init_db():
    db = await _get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            youtube_downloads INTEGER DEFAULT 0,
            tiktok_downloads INTEGER DEFAULT 0,
            instagram_downloads INTEGER DEFAULT 0,
            spotify_downloads INTEGER DEFAULT 0
        )
    """)
    await db.commit()
    logger.info("Database initialized")


async def add_user(user_id: int):
    db = await _get_db()
    await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    await db.commit()


async def increment_stat(user_id: int, platform: str):
    valid_platforms = ('youtube', 'tiktok', 'instagram', 'spotify')
    if platform not in valid_platforms:
        return

    db = await _get_db()
    await db.execute(
        f"UPDATE users SET {platform}_downloads = {platform}_downloads + 1 WHERE user_id = ?",
        (user_id,)
    )
    await db.commit()


async def get_user_stats(user_id: int) -> dict | None:
    db = await _get_db()
    async with db.execute(
        "SELECT youtube_downloads, tiktok_downloads, instagram_downloads, spotify_downloads "
        "FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            yt, tt, ig, sp = row[0], row[1], row[2], row[3]
            return {
                'youtube': yt, 'tiktok': tt,
                'instagram': ig, 'spotify': sp,
                'total': yt + tt + ig + sp
            }
        return None


async def get_total_stats() -> dict:
    db = await _get_db()
    async with db.execute(
        "SELECT COALESCE(SUM(youtube_downloads),0), COALESCE(SUM(tiktok_downloads),0), "
        "COALESCE(SUM(instagram_downloads),0), COALESCE(SUM(spotify_downloads),0) FROM users"
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            yt, tt, ig, sp = row[0], row[1], row[2], row[3]
            return {
                'youtube': yt, 'tiktok': tt,
                'instagram': ig, 'spotify': sp,
                'total': yt + tt + ig + sp
            }
        return {'youtube': 0, 'tiktok': 0, 'instagram': 0, 'spotify': 0, 'total': 0}
