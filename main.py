import asyncio
import logging
import os
import json

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from app.config import config
from app.handlers import base, download
from app.database import init_db, close_db

# ─── Logging Setup ──────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Quiet noisy libs
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ─── Bot Profile ────────────────────────────────────────────────────────

async def update_bot_profile(bot: Bot):
    """Update bot display name from partners.json (if configured)."""
    partners_file = os.path.join(os.path.dirname(__file__), 'partners.json')
    if not os.path.exists(partners_file):
        return

    try:
        with open(partners_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        bot_name = data.get('bot_name')
        if bot_name:
            try:
                await bot.set_my_name(name=bot_name)
                logger.info("Bot name set to: %s", bot_name)
            except Exception as e:
                logger.warning("Failed to set bot name: %s", e)
    except Exception as e:
        logger.warning("Error reading partners.json: %s", e)


# ─── Main ───────────────────────────────────────────────────────────────

async def main():
    await init_db()

    if config.use_local_server:
        session = AiohttpSession(
            api=TelegramAPIServer.from_base(config.local_server_url, is_local=False)
        )
        bot = Bot(token=config.bot_token, session=session)
        logger.info("Using local Telegram Bot API server at %s", config.local_server_url)
    else:
        bot = Bot(token=config.bot_token)
        
    dp = Dispatcher()

    dp.include_router(base.router)
    dp.include_router(download.router)

    await update_bot_profile(bot)

    logger.info("Bot starting...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await close_db()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
