import html
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery

from app.database import add_user, get_user_stats, get_total_stats
from app.config import config
import app.keyboards as kb
from app.services.subscription import get_unsubscribed_channels, get_subscription_menu

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    unsub = await get_unsubscribed_channels(message.bot, message.from_user.id)
    if unsub:
        await message.answer(
            "Для использования бота необходимо подписаться на наши каналы:",
            reply_markup=get_subscription_menu(unsub)
        )
        return

    await add_user(message.from_user.id)
    name = html.escape(message.from_user.first_name)
    await message.answer(
        f'👋 Привет {name}. Я помогу тебе скачать видео и аудио '
        f'с различных медиа ресурсов 🎥💾. Выбери соцсеть, чтобы начать',
        reply_markup=kb.get_main_menu()
    )


@router.message(Command('stat'))
async def cmd_stat(message: Message):
    if message.from_user.id != config.admin_id:
        await message.answer('У вас нет доступа к этой функции(', reply_markup=kb.get_main_menu())
        return

    stats = await get_total_stats()
    text = (
        f"📊 <b>Общая статистика бота:</b>\n\n"
        f"Всего скачиваний: {stats['total']}\n"
        f"YouTube: {stats['youtube']}\n"
        f"TikTok: {stats['tiktok']}\n"
        f"Instagram: {stats['instagram']}\n"
        f"Spotify: {stats['spotify']}"
    )
    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == 'main_menu')
async def callback_main_menu(callback: CallbackQuery):
    await callback.answer()
    unsub = await get_unsubscribed_channels(callback.bot, callback.from_user.id)
    if unsub:
        try:
            await callback.message.edit_text(
                "Для использования бота необходимо подписаться на наши каналы:",
                reply_markup=get_subscription_menu(unsub)
            )
        except Exception:
            pass
        return

    try:
        await callback.message.edit_text(
            'Выбери соцсеть, чтобы начать:',
            reply_markup=kb.get_main_menu()
        )
    except Exception:
        pass


@router.callback_query(F.data == 'check_sub')
async def check_subscription(callback: CallbackQuery):
    unsub = await get_unsubscribed_channels(callback.bot, callback.from_user.id)
    if unsub:
        await callback.answer("Вы не подписались на все каналы!", show_alert=True)
    else:
        await callback.answer("✅ Подписка подтверждена!")
        try:
            await callback.message.edit_text(
                "✅ Подписка подтверждена!",
                reply_markup=kb.get_main_menu()
            )
        except Exception:
            pass


@router.callback_query(F.data == 'my_statistics')
async def my_statistics(callback: CallbackQuery):
    await callback.answer()
    stats = await get_user_stats(callback.from_user.id)
    if not stats:
        try:
            await callback.message.edit_text(
                'Ваша статистика пока пуста.',
                reply_markup=kb.get_main_menu()
            )
        except Exception:
            pass
        return

    text = (
        f"⚙️ <b>Ваша статистика:</b>\n"
        f"Всего скачиваний: {stats['total']}\n"
        f"YouTube: {stats['youtube']}\n"
        f"TikTok: {stats['tiktok']}\n"
        f"Instagram: {stats['instagram']}\n"
        f"Spotify: {stats['spotify']}"
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_main_menu())
    except Exception:
        pass


# ─── Platform Sub-Menus ────────────────────────────────────────────────

@router.callback_query(F.data == 'menu_youtube')
async def inline_youtube(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text('Выбери режим для YouTube:', reply_markup=kb.get_youtube_menu())
    except Exception:
        pass


@router.callback_query(F.data == 'menu_tiktok')
async def inline_tiktok(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text('Выбери режим для TikTok:', reply_markup=kb.get_tiktok_menu())
    except Exception:
        pass
