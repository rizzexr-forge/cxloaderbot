import re
import os
import html
import asyncio
import logging
import time

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import app.keyboards as kb
from app.services.downloader import download_video, download_audio, get_tiktok_meta, get_video_info
from app.services.spotify import get_spotify_track_info, SpotifyError
from app.services.cleaner import cleanup_file
from app.services.error_logger import log_error
from app.services.subscription import get_unsubscribed_channels, get_subscription_menu, get_watermark
from app.database import increment_stat
from app.limits_config import load_limits

logger = logging.getLogger(__name__)
router = Router()

DOWNLOAD_COOLDOWN_SEC = 60  # cooldown after a completed download

# Active downloads: user_id -> True if currently downloading
_user_downloading: dict[int, bool] = {}
# Cooldown timestamps: user_id -> timestamp when cooldown expires
_user_cooldown: dict[int, float] = {}


def _check_rate_limit(user_id: int) -> str | None:
    """Return an error message if user is rate-limited, else None."""
    # Check if currently downloading
    if _user_downloading.get(user_id):
        return "⏳ <b>Подождите!</b>\nУ вас уже идёт скачивание. Дождитесь его завершения."
    # Check cooldown
    cd = _user_cooldown.get(user_id, 0)
    remaining = cd - time.time()
    if remaining > 0:
        secs = int(remaining)
        return f"⏳ <b>Подождите ещё {secs} сек.</b>\nМежду скачиваниями должно пройти {DOWNLOAD_COOLDOWN_SEC} секунд."
    return None


class DownloadState(StatesGroup):
    url = State()
    quality = State()


# ─── Subscription check helper ─────────────────────────────────────────

async def _check_sub(bot, user_id) -> list:
    return await get_unsubscribed_channels(bot, user_id)


async def _sub_gate_callback(callback: CallbackQuery) -> bool:
    """Check subscription. Returns True if user is NOT subscribed (blocked)."""
    unsub = await _check_sub(callback.bot, callback.from_user.id)
    if unsub:
        try:
            await callback.message.edit_text(
                "Для использования бота необходимо подписаться на наши каналы:",
                reply_markup=get_subscription_menu(unsub)
            )
        except Exception:
            pass
        return True
    return False


async def _sub_gate_message(message: Message) -> bool:
    """Check subscription. Returns True if user is NOT subscribed (blocked)."""
    unsub = await _check_sub(message.bot, message.from_user.id)
    if unsub:
        await message.answer(
            "Для использования бота необходимо подписаться на наши каналы:",
            reply_markup=get_subscription_menu(unsub)
        )
        return True
    return False


# ─── Cancel ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'download_cancel')
async def cancel_download(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    try:
        await callback.message.edit_text(
            "❌ Действие отменено. Выберите в меню:",
            reply_markup=kb.get_main_menu()
        )
    except Exception:
        pass


# ─── YouTube ────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'menu_youtube_video')
async def ask_youtube_video(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if await _sub_gate_callback(callback):
        return
    await state.set_state(DownloadState.url)
    await state.update_data(platform='youtube', type='video')
    try:
        await callback.message.edit_text(
            '💬 <b>Отправь ссылку на YouTube Видео/Shorts</b>',
            parse_mode="HTML", reply_markup=kb.get_cancel_menu()
        )
    except Exception:
        pass


@router.callback_query(F.data == 'menu_youtube_audio')
async def ask_youtube_audio(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if await _sub_gate_callback(callback):
        return
    await state.set_state(DownloadState.url)
    await state.update_data(platform='youtube', type='audio')
    try:
        await callback.message.edit_text(
            '💬 <b>Отправь ссылку на YouTube Видео</b>, и я извлеку из него звук',
            parse_mode="HTML", reply_markup=kb.get_cancel_menu()
        )
    except Exception:
        pass


# ─── TikTok ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'menu_tiktok_video')
async def ask_tiktok_video(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if await _sub_gate_callback(callback):
        return
    await state.set_state(DownloadState.url)
    await state.update_data(platform='tiktok', type='video')
    try:
        await callback.message.edit_text(
            '💬 <b>Отправь ссылку на TikTok Видео</b>',
            parse_mode="HTML", reply_markup=kb.get_cancel_menu()
        )
    except Exception:
        pass


@router.callback_query(F.data == 'menu_tiktok_audio')
async def ask_tiktok_audio(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if await _sub_gate_callback(callback):
        return
    await state.set_state(DownloadState.url)
    await state.update_data(platform='tiktok', type='audio')
    try:
        await callback.message.edit_text(
            '💬 <b>Отправь ссылку на TikTok Видео</b>, и я извлеку из него звук',
            parse_mode="HTML", reply_markup=kb.get_cancel_menu()
        )
    except Exception:
        pass


# ─── Instagram ──────────────────────────────────────────────────────────

@router.callback_query(F.data == 'menu_instagram')
async def ask_instagram(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if await _sub_gate_callback(callback):
        return
    await state.set_state(DownloadState.url)
    await state.update_data(platform='instagram', type='video')
    try:
        await callback.message.edit_text(
            '💬 <b>Отправь ссылку на Instagram Reels/Post</b>',
            parse_mode="HTML", reply_markup=kb.get_cancel_menu()
        )
    except Exception:
        pass


# ─── Spotify ────────────────────────────────────────────────────────────

@router.callback_query(F.data == 'menu_spotify')
async def ask_spotify(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if await _sub_gate_callback(callback):
        return
    await state.set_state(DownloadState.url)
    await state.update_data(platform='spotify', type='audio')
    try:
        await callback.message.edit_text(
            '💬 <b>Отправь ссылку на трек из Spotify</b>\n'
            '<code>Мы найдем его и скачаем в лучшем качестве!</code>',
            parse_mode="HTML", reply_markup=kb.get_cancel_menu()
        )
    except Exception:
        pass


# ─── URL Processing ────────────────────────────────────────────────────

@router.message(DownloadState.url)
async def process_url(message: Message, state: FSMContext):
    url = message.text
    if not url:
        await message.answer("❌ Пожалуйста, отправьте ссылку.")
        return

    data = await state.get_data()
    platform = data.get('platform')
    media_type = data.get('type')

    # YouTube video → ask quality
    if platform == 'youtube' and media_type == 'video':
        await state.update_data(url=url)
        await state.set_state(DownloadState.quality)

        progress_msg_tmp = await message.answer(
            '🔍 <b>Анализирую видео...</b>\n<code>Пожалуйста, подождите...</code>',
            parse_mode="HTML"
        )
        try:
            info = await get_video_info(url, 'youtube')
            try:
                await progress_msg_tmp.delete()
            except Exception:
                pass
            text = (
                f"📺 <b>{html.escape(info['title'])}</b>\n"
                f"👤 {html.escape(info['channel'])}\n"
                f"⏱ {info['duration']} сек.\n\n"
                "👇 Выберите качество:"
            )
            keyboard = kb.get_dynamic_quality_menu(info['qualities'], 'youtube')
            if info['thumbnail']:
                await message.answer_photo(photo=info['thumbnail'], caption=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.error("Error getting video info: %s", e)
            try:
                await progress_msg_tmp.edit_text("❌ Ошибка при получении информации о видео.")
            except Exception:
                pass
            await state.clear()
        return

    await state.clear()
    progress_msg = await message.answer(
        '🚀 <b>Скачиваю...</b>\n<code>Пожалуйста, подождите...</code>',
        parse_mode="HTML"
    )
    await perform_download(message, progress_msg, url, platform, media_type, message.from_user.id)


# ─── Direct URL Detection ──────────────────────────────────────────────

@router.message(F.text.regexp(r'https?://[^\s]+'))
async def process_direct_url(message: Message, state: FSMContext):
    # If already waiting for URL via menus, forward to regular flow
    current_state = await state.get_state()
    if current_state == DownloadState.url:
        return await process_url(message, state)

    url = message.text
    if not url:
        return

    # Subscription check
    if await _sub_gate_message(message):
        return

    # Detect platform
    url_lower = url.lower()
    platform = None
    media_type = None

    if 'instagram.com' in url_lower:
        platform, media_type = 'instagram', 'video'
    elif 'spotify.com' in url_lower:
        platform, media_type = 'spotify', 'audio'
    elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        platform = 'youtube'
    elif 'tiktok.com' in url_lower or 'vm.tiktok.com' in url_lower or 'vt.tiktok.com' in url_lower:
        platform = 'tiktok'
    else:
        await message.answer("❌ Извините, я не могу распознать и обработать данную ссылку.")
        return

    # TikTok: pre-fetch meta to detect photos vs video
    tiktok_meta = None
    is_tiktok_gallery = False
    if platform == 'tiktok':
        progress_msg_tmp = await message.answer(
            '🔍 <b>Анализирую ссылку...</b>\n<code>Пожалуйста, подождите...</code>',
            parse_mode="HTML"
        )
        try:
            tiktok_meta = await get_tiktok_meta(url)
            result_data = tiktok_meta.get('data', {})
            images = result_data.get('images')
            if images and len(images) > 0:
                is_tiktok_gallery = True
                media_type = 'video'  # gallery — auto-download
        except Exception as e:
            logger.warning("TikTok meta pre-fetch failed: %s", e)
        try:
            await progress_msg_tmp.delete()
        except Exception:
            pass

    # Auto-download for Instagram, Spotify, or TikTok galleries
    if platform == 'youtube':
        progress_msg_tmp = await message.answer(
            '🔍 <b>Анализирую видео...</b>\n<code>Пожалуйста, подождите...</code>',
            parse_mode="HTML"
        )
        try:
            info = await get_video_info(url, 'youtube')
            try:
                await progress_msg_tmp.delete()
            except Exception:
                pass

            text = (
                f"📺 <b>{html.escape(info['title'])}</b>\n"
                f"👤 {html.escape(info['channel'])}\n"
                f"⏱ {info['duration']} сек.\n\n"
                "👇 Выберите формат:"
            )

            keyboard = kb.get_dynamic_quality_menu(info['qualities'], 'youtube')

            await state.set_state(DownloadState.quality)
            await state.update_data(url=url, platform='youtube', type='video', is_direct=True)

            if info['thumbnail']:
                await message.answer_photo(
                    photo=info['thumbnail'],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.error("Error getting YouTube info: %s", e)
            try:
                await progress_msg_tmp.edit_text("❌ Ошибка при получении информации о видео.")
            except Exception:
                pass
    elif platform in ('instagram', 'spotify') or (platform == 'tiktok' and is_tiktok_gallery):
        # Auto-download: Instagram, Spotify, or TikTok photo galleries
        progress_msg = await message.answer(
            '🚀 <b>Скачиваю...</b>\n<code>Пожалуйста, подождите...</code>',
            parse_mode="HTML"
        )
        await perform_download(message, progress_msg, url, platform, media_type, message.from_user.id, tiktok_meta=tiktok_meta)
    else:
        # Ask user to pick format (TikTok non-gallery videos, etc.)
        await state.set_state(DownloadState.url)
        await state.update_data(url=url, platform=platform, is_direct=True, tiktok_meta=tiktok_meta)
        await message.answer("Выберите формат для скачивания:", reply_markup=kb.get_format_menu())


# ─── Direct Format Selection ───────────────────────────────────────────

@router.callback_query(F.data.in_(['direct_format_video', 'direct_format_audio']))
async def process_direct_format(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    if not data.get('is_direct'):
        return

    url = data.get('url')
    platform = data.get('platform')
    media_type = 'video' if callback.data == 'direct_format_video' else 'audio'

    # YouTube video → ask quality first
    if platform == 'youtube' and media_type == 'video':
        await state.update_data(type='video')
        await state.set_state(DownloadState.quality)
        try:
            await callback.message.edit_text(
                "📺 <b>Выберите качество видео:</b>",
                parse_mode="HTML", reply_markup=kb.get_youtube_quality_menu()
            )
        except Exception:
            pass
        return

    await state.clear()
    try:
        progress_msg = await callback.message.edit_text(
            '🚀 <b>Скачиваю...</b>\n<code>Пожалуйста, подождите...</code>',
            parse_mode="HTML"
        )
    except Exception:
        progress_msg = await callback.message.answer(
            '🚀 <b>Скачиваю...</b>\n<code>Пожалуйста, подождите...</code>',
            parse_mode="HTML"
        )
    tiktok_meta = data.get('tiktok_meta')
    await perform_download(
        callback.message, progress_msg, url, platform, media_type,
        callback.from_user.id, tiktok_meta=tiktok_meta
    )


# ─── YouTube Quality ───────────────────────────────────────────────────

@router.callback_query(DownloadState.quality, F.data.startswith('yt_quality_'))
async def process_quality(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    resolution = callback.data.split('_')[-1]
    data = await state.get_data()
    url = data.get('url')
    platform = data.get('platform', 'youtube')

    if resolution == 'audio':
        media_type = 'audio'
        resolution_arg = None
        progress_text = '🚀 <b>Скачиваю звук...</b>\n<code>Пожалуйста, подождите...</code>'
    else:
        media_type = 'video'
        resolution_arg = resolution
        progress_text = f'🚀 <b>Скачиваю в {html.escape(resolution)}p...</b>\n<code>Пожалуйста, подождите...</code>'

    await state.clear()

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=progress_text, parse_mode="HTML"
            )
            progress_msg = callback.message
        else:
            progress_msg = await callback.message.edit_text(
                progress_text, parse_mode="HTML"
            )
    except Exception:
        progress_msg = await callback.message.answer(
            progress_text, parse_mode="HTML"
        )

    await perform_download(
        callback.message, progress_msg, url, platform, media_type,
        callback.from_user.id, resolution_arg
    )


# ─── Safe message editor ───────────────────────────────────────────────

async def _safe_edit(msg: Message, text: str, reply_markup=None):
    """Edit a message safely — handles both photo (caption) and text messages."""
    try:
        if msg.photo:
            await msg.edit_caption(caption=text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        logger.warning("Could not edit message: %s", e)


# ─── Core Download Logic ───────────────────────────────────────────────

async def perform_download(
    message: Message,
    progress_msg: Message,
    url: str,
    platform: str,
    media_type: str,
    user_id: int,
    resolution: str = None,
    tiktok_meta: dict = None
):
    # Rate limit check
    limit_msg = _check_rate_limit(user_id)
    if limit_msg:
        await _safe_edit(progress_msg, limit_msg, reply_markup=kb.get_main_menu())
        return

    _user_downloading[user_id] = True
    file_path = None
    try:
        # Spotify: search via yt-dlp
        if platform == 'spotify':
            await _safe_edit(
                progress_msg,
                '🔍 <b>Ищу трек...</b>\n<code>Пожалуйста, подождите...</code>'
            )
            track_query = await get_spotify_track_info(url)
            search_url = f"ytsearch1:{track_query}"
            result = await download_audio(search_url, 'youtube')
        elif media_type == 'video':
            result = await download_video(url, platform, resolution, tiktok_meta=tiktok_meta)
        else:
            result = await download_audio(url, platform)

        file_path = result.get('file_path')

        if not file_path:
            raise Exception("Файл не был скачан. Возможно, ссылка недоступна (приватный аккаунт или неверный формат).")

        # Validate file exists (for non-gallery)
        if not isinstance(file_path, list) and not os.path.exists(file_path):
            raise Exception("Файл не был скачан или не найден на диске.")

        watermark = get_watermark()
        caption = f"🤖 {html.escape(watermark)}"

        # Calculate total file size
        if isinstance(file_path, list):
            file_size = sum(os.path.getsize(p) for p in file_path if os.path.exists(p))
        else:
            file_size = os.path.getsize(file_path)

        limits = load_limits()
        max_size = limits.get("MAX_VIDEO_SIZE_MB", 500) * 1024 * 1024

        if file_size > max_size:
            text = (
                "⚠️ <b>Файл слишком большой!</b>\n\n"
                f"Мы можем отправить максимум {max_size // (1024 * 1024)} МБ.\n"
                "К сожалению, ваше видео превышает этот лимит. 😔\n"
            )
            if platform == 'youtube' and media_type == 'video' and resolution != '360':
                text += "\n💡 Попробуйте выбрать меньшее качество видео (например 360p или 480p)."

            await _safe_edit(progress_msg, text, reply_markup=kb.get_main_menu())
        else:
            await _safe_edit(
                progress_msg,
                '⬆️ <b>Загружаю в Telegram...</b>\n<code>Осталось немного...</code>'
            )

            is_gallery = result.get('is_gallery', False)

            if is_gallery and isinstance(file_path, list):
                # Notify about photo limit
                photos_limited = result.get('photos_limited', False)
                if photos_limited:
                    original_count = result.get('original_count', 0)
                    max_photos = limits.get('MAX_TIKTOK_PHOTOS', 35)
                    await message.answer(
                        f"⚠️ <b>Внимание:</b> В этом TikTok {original_count} фото.\n"
                        f"Мы скачали и отправим только первые {max_photos} для соблюдения лимитов.",
                        parse_mode="HTML"
                    )

                # Send in groups of 10 (Telegram limit)
                media_group = []
                for idx, path in enumerate(file_path):
                    if idx == 0:
                        media_group.append(InputMediaPhoto(media=FSInputFile(path), caption=caption, parse_mode="HTML"))
                    else:
                        media_group.append(InputMediaPhoto(media=FSInputFile(path)))

                for i in range(0, len(media_group), 10):
                    chunk = media_group[i:i + 10]
                    for attempt in range(3):
                        try:
                            await message.answer_media_group(media=chunk)
                            break
                        except Exception as e:
                            if attempt == 2:
                                await message.answer(
                                    f"⚠️ Ошибка при отправке фото: {html.escape(str(e)[:50])}..."
                                )
                            else:
                                await asyncio.sleep(2)

                    if i + 10 < len(media_group):
                        await asyncio.sleep(1.5)
            else:
                # Single file — detect type by extension
                ext = os.path.splitext(file_path)[1].lower()
                file_obj = FSInputFile(file_path)

                if ext in ('.jpg', '.jpeg', '.png', '.webp'):
                    await message.answer_photo(photo=file_obj, caption=caption, parse_mode="HTML")
                elif media_type == 'video' or ext in ('.mp4', '.mov', '.avi', '.mkv'):
                    await message.answer_video(video=file_obj, caption=caption, parse_mode="HTML", supports_streaming=True)
                else:
                    await message.answer_audio(audio=file_obj, caption=caption, parse_mode="HTML")

            try:
                await progress_msg.delete()
            except Exception:
                pass

            await increment_stat(user_id, platform)
            # Set cooldown
            _user_cooldown[user_id] = time.time() + DOWNLOAD_COOLDOWN_SEC
            await message.answer(
                '✅ <b>Успешно!</b>\nРеклама отсутствует 😉\n\nЧто-нибудь еще?',
                parse_mode="HTML", reply_markup=kb.get_main_menu()
            )

    except Exception as e:
        error_text = str(e)
        logger.error("Download failed [%s/%s] url=%s: %s", platform, media_type, url, error_text[:200])
        await log_error(user_id, platform, media_type, url, error_text)

        safe_detail = html.escape(error_text[:80])
        await _safe_edit(
            progress_msg,
            "❌ <b>Не удалось скачать.</b>\n\n"
            "Возможные причины:\n"
            "• Видео недоступно или удалено\n"
            "• Ограничение по возрасту\n"
            "• Ошибка сети\n\n"
            "Попробуйте другую ссылку.\n\n"
            f"<code>{safe_detail}</code>",
            reply_markup=kb.get_main_menu()
        )

    finally:
        _user_downloading.pop(user_id, None)
        if file_path:
            paths = file_path if isinstance(file_path, list) else [file_path]
            for path in paths:
                if os.path.exists(path):
                    asyncio.create_task(cleanup_file(path, delay=3))
