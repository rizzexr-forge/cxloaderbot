import aiomysql
import logging

from app.config import config

logger = logging.getLogger(__name__)

# Connection pool — reused across the entire bot lifetime
_pool: aiomysql.Pool | None = None


async def init_db():
    """Create connection pool and ensure the users table exists."""
    global _pool
    _pool = await aiomysql.create_pool(
        host=config.db_host,
        port=config.db_port,
        db=config.db_name,
        user=config.db_user,
        password=config.db_pass,
        minsize=2,
        maxsize=10,
        autocommit=True
    )
    logger.info("Database pool created (%s@%s:%s/%s)", config.db_user, config.db_host, config.db_port, config.db_name)

    async with _pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    youtube INTEGER DEFAULT 0,
                    tiktok INTEGER DEFAULT 0,
                    instagram INTEGER DEFAULT 0,
                    spotify INTEGER DEFAULT 0,
                    registration_date DATE DEFAULT (CURRENT_DATE),
                    premium BOOLEAN DEFAULT FALSE,
                    `ban` BOOLEAN DEFAULT FALSE
                )
            """)
    logger.info("Table 'users' ensured")


async def close_db():
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("Database pool closed")


async def add_user(user_id: int):
    """Insert a new user if not already present."""
    async with _pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT IGNORE INTO users (user_id) VALUES (%s)",
                (user_id,),
            )


async def increment_stat(user_id: int, platform: str):
    """Increment download counter for the given platform."""
    valid = ('youtube', 'tiktok', 'instagram', 'spotify')
    if platform not in valid:
        return
    async with _pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"UPDATE users SET {platform} = {platform} + 1 WHERE user_id = %s",
                (user_id,),
            )


async def get_user_stats(user_id: int) -> dict | None:
    """Return download stats for one user."""
    async with _pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT youtube, tiktok, instagram, spotify FROM users WHERE user_id = %s",
                (user_id,),
            )
            row = await cur.fetchone()
    if row:
        yt, tt, ig, sp = row['youtube'], row['tiktok'], row['instagram'], row['spotify']
        return {
            'youtube': yt, 'tiktok': tt,
            'instagram': ig, 'spotify': sp,
            'total': yt + tt + ig + sp,
        }
    return None


async def get_total_stats() -> dict:
    """Return aggregate download stats across all users."""
    async with _pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT COALESCE(SUM(youtube),0) AS yt, COALESCE(SUM(tiktok),0) AS tt, "
                "COALESCE(SUM(instagram),0) AS ig, COALESCE(SUM(spotify),0) AS sp FROM users"
            )
            row = await cur.fetchone()
    if row:
        yt, tt, ig, sp = row['yt'], row['tt'], row['ig'], row['sp']
        return {
            'youtube': yt, 'tiktok': tt,
            'instagram': ig, 'spotify': sp,
            'total': int(yt + tt + ig + sp),
        }
    return {'youtube': 0, 'tiktok': 0, 'instagram': 0, 'spotify': 0, 'total': 0}
