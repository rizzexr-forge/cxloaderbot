import asyncio
import os
import random
import string
import logging
import time

from yt_dlp import YoutubeDL
import imageio_ffmpeg

from app.limits_config import load_limits

logger = logging.getLogger(__name__)

# Absolute path to cookies file (project root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
USER_COOKIES_FILE = os.path.join(_PROJECT_ROOT, "cookies.txt")

# TikWM API base
_TIKWM_API = "https://tikwm.com/api/"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


# ─── Helpers ────────────────────────────────────────────────────────────

def _generate_filename() -> str:
    """Generate a random 20-char filename (no async needed)."""
    chars = random.choices(string.ascii_letters + string.digits, k=20)
    random.shuffle(chars)
    return ''.join(chars)


def _get_base_ydl_opts(output_path: str) -> dict:
    """Base yt-dlp options shared by video and audio downloads."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    limits = load_limits()
    max_duration = limits.get("MAX_VIDEO_DURATION_SEC", 3600)

    def match_filter(info, incomplete):
        duration = info.get('duration')
        if duration and duration > max_duration:
            return f"Видео слишком длинное. Лимит: {max_duration} сек."
        return None

    opts = {
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'ffmpeg_location': ffmpeg_exe,
        'match_filter': match_filter,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'socket_timeout': 60,
        'retries': 10,
        'fragment_retries': 10,
        'extractor_retries': 5,
        'file_access_retries': 5,
        'http_chunk_size': 10485760,  # 10MB chunks
        'ignoreerrors': False,
        'no_color': True,
        # Modern User-Agent to avoid bot detection
        'http_headers': {
            'User-Agent': _UA,
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },

    }
    if os.path.exists(USER_COOKIES_FILE):
        opts['cookiefile'] = USER_COOKIES_FILE
    return opts


# ─── TikTok via TikWM API ──────────────────────────────────────────────

async def get_tiktok_meta(url: str, retries: int = 3) -> dict:
    """Fetch TikTok metadata from TikWM API with retries."""
    import urllib.request
    import urllib.parse
    import json as _json

    api_url = f"{_TIKWM_API}?url={urllib.parse.quote(url)}"
    req = urllib.request.Request(api_url, headers={
        'User-Agent': _UA,
        'Accept': 'application/json, text/plain, */*'
    })

    def _fetch():
        with urllib.request.urlopen(req, timeout=15) as response:
            return _json.loads(response.read().decode())

    last_err = None
    for attempt in range(retries):
        try:
            data = await asyncio.to_thread(_fetch)
            if data and data.get('code') == 0:
                return data
        except Exception as e:
            last_err = e
            logger.warning("TikWM API attempt %d failed: %s", attempt + 1, e)
        if attempt < retries - 1:
            await asyncio.sleep(1.5)

    # Final attempt
    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        raise Exception(f"TikWM API недоступен после {retries} попыток: {last_err or e}")


def _download_bytes(url: str, dest_path: str, timeout: int = 30, retries: int = 4):
    """Download a URL to a file with retry, content-length verification, and chunked reading."""
    import urllib.request
    import urllib.error

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': _UA})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content_length = response.headers.get('Content-Length')
                expected_size = int(content_length) if content_length else None

                downloaded = 0
                with open(dest_path, 'wb') as out_file:
                    while True:
                        chunk = response.read(1048576)  # 1MB
                        if not chunk:
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)

                # Verify completeness
                if expected_size and downloaded < expected_size:
                    raise Exception(
                        f"Incomplete download: got {downloaded}/{expected_size} bytes"
                    )
                return
        except Exception as e:
            if attempt == retries - 1:
                # Clean up partial file
                if os.path.exists(dest_path):
                    try:
                        os.remove(dest_path)
                    except OSError:
                        pass
                raise Exception(f"Download failed after {retries} attempts: {e}")
            time.sleep(2 * (attempt + 1))  # Progressive backoff


async def download_tiktok_tikwm(url: str, pre_fetched_data: dict = None) -> dict:
    """Download TikTok content via TikWM API (supports both video and photo galleries)."""
    limits = load_limits()
    max_photos = limits.get("MAX_TIKTOK_PHOTOS", 35)
    max_duration = limits.get("MAX_VIDEO_DURATION_SEC", 3600)

    data = pre_fetched_data if pre_fetched_data else await get_tiktok_meta(url)

    if data.get('code') != 0:
        raise Exception("Не удалось получить данные с TikTok (API error)")

    result_data = data.get('data', {})
    title = result_data.get('title', 'Без названия')

    output_dir = os.path.join(_PROJECT_ROOT, 'temp_downloads')
    os.makedirs(output_dir, exist_ok=True)

    # === Photo gallery ===
    images = result_data.get('images')
    if images and len(images) > 0:
        original_count = len(images)
        photos_limited = original_count > max_photos
        if photos_limited:
            images = images[:max_photos]

        file_paths = []
        for idx, img_url in enumerate(images):
            file_name = f"{_generate_filename()}_{idx}.jpg"
            file_path = os.path.join(output_dir, file_name)
            await asyncio.to_thread(_download_bytes, img_url, file_path, timeout=15, retries=4)
            file_paths.append(file_path)

        return {
            "file_path": file_paths,
            "title": title,
            "duration": 0,
            "is_gallery": True,
            "photos_limited": photos_limited,
            "original_count": original_count
        }

    # === Video ===
    duration = result_data.get('duration', 0)
    if duration > max_duration:
        raise Exception(f"Видео слишком длинное ({duration}с). Лимит — {max_duration}с.")

    play_url = result_data.get('play')
    if not play_url:
        raise Exception("Видео не найдено в ответе TikWM")

    file_name = f"{_generate_filename()}.mp4"
    file_path = os.path.join(output_dir, file_name)
    await asyncio.to_thread(_download_bytes, play_url, file_path, timeout=60, retries=4)

    return {
        "file_path": file_path,
        "title": title,
        "duration": duration,
        "is_gallery": False
    }


# ─── YouTube Metadata Extraction ───────────────────────────────────────

async def get_video_info(url: str, platform: str) -> dict:
    """Fetch video metadata without downloading, group available formats by resolution."""
    if platform != 'youtube':
        return {}  # Only used for youtube currently

    opts = _get_base_ydl_opts('')
    # We only need metadata — extract_info(download=False) returns all formats
    # regardless of this setting, but we set it to avoid yt-dlp warnings
    opts['format'] = 'best'

    def _extract():
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    info = await asyncio.to_thread(_extract)

    title = info.get('title', 'Без названия')
    thumbnail = info.get('thumbnail')
    channel = info.get('uploader', 'Неизвестно')
    duration = info.get('duration', 0)

    formats = info.get('formats', [])

    logger.info("get_video_info: found %d formats for %s", len(formats), url)
    for f in formats:
        h = f.get('height')
        fs = f.get('filesize') or f.get('filesize_approx')
        vc = f.get('vcodec')
        ac = f.get('acodec')
        fid = f.get('format_id')
        if h:
            logger.debug("  format %s: %sp, size=%s, vcodec=%s, acodec=%s", fid, h, fs, vc, ac)

    # We want to find the best audio size to add to video size
    audio_formats = [f for f in formats if f.get('vcodec') in ('none', None) and f.get('acodec') not in ('none', None)]
    best_audio = max(audio_formats, key=lambda x: x.get('filesize') or x.get('filesize_approx') or 0, default={})
    audio_size = best_audio.get('filesize') or best_audio.get('filesize_approx') or 0

    # Target resolutions
    target_resolutions = [144, 240, 360, 480, 720, 1080, 1440, 2160]
    available_qualities = {}  # {standard_res: {'resolution', 'size', 'format_id'}}

    for f in formats:
        # Only consider formats that have video
        height = f.get('height')
        vcodec = f.get('vcodec')
        if not height or vcodec in ('none', None):
            continue

        # Find closest standard resolution if it's slightly off
        standard_res = None
        for res in target_resolutions:
            if abs(height - res) <= 30:  # Wider tolerance
                standard_res = res
                break

        if not standard_res:
            # Also accept non-standard resolutions and map to nearest
            closest = min(target_resolutions, key=lambda r: abs(height - r))
            if abs(height - closest) <= 60:
                standard_res = closest

        if standard_res:
            v_size = f.get('filesize') or f.get('filesize_approx') or 0
            # If video format already includes audio (acodec != none), don't add audio_size
            has_audio = f.get('acodec') and f.get('acodec') != 'none'
            total_size = v_size + (0 if has_audio else audio_size) if v_size else 0

            # Prefer formats with known size; among known sizes, pick largest (best quality)
            existing = available_qualities.get(standard_res)
            if not existing:
                available_qualities[standard_res] = {
                    'resolution': str(standard_res),
                    'size': total_size,
                    'format_id': f.get('format_id')
                }
            elif total_size > existing['size']:
                available_qualities[standard_res] = {
                    'resolution': str(standard_res),
                    'size': total_size,
                    'format_id': f.get('format_id')
                }

    logger.info("get_video_info: available resolutions = %s", list(available_qualities.keys()))

    # Format the sizes
    def format_size(bytes_size):
        if not bytes_size:
            return ""
        mb = bytes_size / (1024 * 1024)
        if mb >= 1000:
            return f"{mb / 1024:.1f}GB"
        return f"{mb:.1f}MB"

    qualities_list = []
    for res in sorted(available_qualities.keys()):
        size_str = format_size(available_qualities[res]['size'])
        label = f"{res}p"
        qualities_list.append({
            'label': label,
            'resolution': str(res),
            'size_bytes': available_qualities[res]['size'],
            'size_formatted': size_str
        })

    return {
        'title': title,
        'thumbnail': thumbnail,
        'channel': channel,
        'duration': duration,
        'qualities': qualities_list,
        'audio_size_formatted': format_size(audio_size)
    }

# ─── Universal Video Download ──────────────────────────────────────────

async def download_video(url: str, platform: str, resolution: str = None, tiktok_meta: dict = None) -> dict:
    """Download video from YouTube, TikTok, or Instagram."""
    if platform == 'tiktok':
        try:
            return await download_tiktok_tikwm(url, tiktok_meta)
        except Exception as e:
            logger.warning("TikWM failed for %s: %s — falling back to yt-dlp", url, e)

    file_id = _generate_filename()
    output_dir = os.path.join(_PROJECT_ROOT, 'temp_downloads')
    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, f"{file_id}.%(ext)s")

    opts = _get_base_ydl_opts(outtmpl)
    # Override quiet so we can see errors in logs
    opts['quiet'] = False
    opts['no_warnings'] = False

    if platform == 'youtube':
        if resolution:
            # Comprehensive fallback chain: mp4 first, then any format, then absolute best
            opts['format'] = (
                f'bestvideo[height<={resolution}][ext=mp4]+bestaudio[ext=m4a]/'
                f'bestvideo[height<={resolution}]+bestaudio/'
                f'best[height<={resolution}][ext=mp4]/'
                f'best[height<={resolution}]/'
                f'bestvideo+bestaudio/best'
            )
        else:
            opts['format'] = (
                'bestvideo[ext=mp4]+bestaudio[ext=m4a]/'
                'bestvideo+bestaudio/'
                'best[ext=mp4]/'
                'best'
            )
        opts['merge_output_format'] = 'mp4'
    elif platform == 'instagram':
        opts['format'] = 'best'
        opts['merge_output_format'] = 'mp4'
    elif platform == 'tiktok':
        opts['format'] = (
            'bestvideo[ext=mp4]+bestaudio[ext=m4a]/'
            'bestvideo+bestaudio/'
            'best[ext=mp4]/best'
        )
        opts['merge_output_format'] = 'mp4'

    # Track what was actually downloaded
    downloaded_files = []

    def _progress_hook(d):
        if d.get('status') == 'finished':
            fn = d.get('filename')
            if fn:
                downloaded_files.append(fn)
                logger.info("yt-dlp finished downloading: %s", fn)

    opts['progress_hooks'] = [_progress_hook]

    def _download():
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    try:
        info = await asyncio.to_thread(_download)
    except Exception as e:
        logger.error("yt-dlp extract_info EXCEPTION for %s: %s", url, e)
        # Clean up partial files
        for f in os.listdir(output_dir):
            if f.startswith(file_id):
                try:
                    os.remove(os.path.join(output_dir, f))
                except OSError:
                    pass
        raise Exception(f"Ошибка yt-dlp: {str(e)[:150]}")

    # Log what we got
    logger.info("yt-dlp completed. downloaded_files from hooks: %s", downloaded_files)

    # Try to find the final file
    downloaded_file = None

    # Method 1: requested_downloads (best source)
    requested_downloads = info.get('requested_downloads')
    if requested_downloads and isinstance(requested_downloads, list):
        downloaded_file = requested_downloads[0].get('filepath')
        logger.info("Method 1 (requested_downloads): %s", downloaded_file)

    # Method 2: info dict keys
    if not downloaded_file or not os.path.exists(str(downloaded_file or '')):
        downloaded_file = info.get('filepath') or info.get('_filename')
        logger.info("Method 2 (info dict): %s", downloaded_file)

    # Method 3: progress hook results
    if not downloaded_file or not os.path.exists(str(downloaded_file or '')):
        if downloaded_files:
            # The last downloaded file after merge will be the final one
            # But check for the merged .mp4 first
            for hook_file in reversed(downloaded_files):
                if os.path.exists(hook_file):
                    downloaded_file = hook_file
                    logger.info("Method 3 (progress hook): %s", downloaded_file)
                    break

    # Method 4: scan directory
    if not downloaded_file or not os.path.exists(str(downloaded_file or '')):
        found_files = [f for f in os.listdir(output_dir)
                       if f.startswith(file_id) and not f.endswith('.part')]
        logger.info("Method 4 (dir scan): found %s", found_files)
        if found_files:
            mp4_files = [f for f in found_files if f.endswith('.mp4')]
            chosen = mp4_files[0] if mp4_files else found_files[0]
            downloaded_file = os.path.join(output_dir, chosen)

    if not downloaded_file or not os.path.exists(str(downloaded_file or '')):
        all_files = os.listdir(output_dir)
        logger.error("ALL METHODS FAILED. file_id=%s, dir contents: %s, hook files: %s",
                      file_id, all_files, downloaded_files)
        raise Exception("yt-dlp не сохранил файл. Возможно, контент недоступен.")

    logger.info("Final downloaded file: %s (size: %d bytes)",
                downloaded_file, os.path.getsize(downloaded_file))

    return {
        "file_path": downloaded_file,
        "title": info.get('title', 'Без названия'),
        "duration": info.get('duration', 0)
    }


# ─── Universal Audio Download ──────────────────────────────────────────

async def download_audio(url: str, platform: str) -> dict:
    """Download and extract audio as MP3."""
    file_name = _generate_filename()
    output_dir = os.path.join(_PROJECT_ROOT, 'temp_downloads')
    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, f"{file_name}.%(ext)s")

    # TikTok /photo/ URLs → swap to /video/ for yt-dlp compatibility
    if platform == 'tiktok' and '/photo/' in url:
        url = url.replace('/photo/', '/video/')

    opts = _get_base_ydl_opts(outtmpl)
    opts['format'] = 'bestaudio/best'
    opts['postprocessors'] = [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }]

    def _download():
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    info = await asyncio.to_thread(_download)

    # Find the MP3 first, then any file as fallback
    downloaded_file = None
    for f in os.listdir(output_dir):
        if f.startswith(file_name) and f.endswith('.mp3'):
            downloaded_file = os.path.join(output_dir, f)
            break

    if not downloaded_file:
        for f in os.listdir(output_dir):
            if f.startswith(file_name):
                downloaded_file = os.path.join(output_dir, f)
                break

    if not downloaded_file:
        raise Exception("yt-dlp не сохранил аудиофайл. Возможно, контент недоступен.")

    return {
        "file_path": downloaded_file,
        "title": info.get('title', 'Без названия'),
        "duration": info.get('duration', 0)
    }
