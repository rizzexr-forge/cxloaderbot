from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='❤️ YouTube', callback_data='menu_youtube'),
         InlineKeyboardButton(text='🖤 TikTok', callback_data='menu_tiktok')],
        [InlineKeyboardButton(text='🧡 Instagram', callback_data='menu_instagram')]
    ])

def get_youtube_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎥 Скачать видео', callback_data='menu_youtube_video')],
        [InlineKeyboardButton(text='🎤 Скачать аудио', callback_data='menu_youtube_audio')],
        [InlineKeyboardButton(text='🔙 Назад', callback_data='main_menu')]
    ])

def get_tiktok_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎥 Скачать видео', callback_data='menu_tiktok_video')],
        [InlineKeyboardButton(text='🎤 Скачать аудио', callback_data='menu_tiktok_audio')],
        [InlineKeyboardButton(text='🔙 Назад', callback_data='main_menu')]
    ])

def get_format_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎥 Скачать видео', callback_data='direct_format_video')],
        [InlineKeyboardButton(text='🎤 Скачать аудио', callback_data='direct_format_audio')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='download_cancel')]
    ])

def get_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='❌ Отмена', callback_data='download_cancel')]
    ])

def get_youtube_quality_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎬 1080p', callback_data='yt_quality_1080'),
         InlineKeyboardButton(text='🎬 720p', callback_data='yt_quality_720')],
        [InlineKeyboardButton(text='🎬 480p', callback_data='yt_quality_480'),
         InlineKeyboardButton(text='🎬 360p', callback_data='yt_quality_360')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='download_cancel')]
    ])

def get_dynamic_quality_menu(qualities: list, platform: str = 'youtube') -> InlineKeyboardMarkup:
    """Generate dynamic quality buttons based on available formats."""
    buttons = []
    
    # We create a 2-column layout for video qualities
    row = []
    # Reverse so best quality is at the top
    for q in reversed(qualities):
        size = q.get('size_formatted', '')
        label = f"🎬 {q['label']} ({size})" if size else f"🎬 {q['label']}"
        cb_data = f"yt_quality_{q['resolution']}"
        row.append(InlineKeyboardButton(text=label, callback_data=cb_data))
        if len(row) == 2:
            buttons.append(row)
            row = []
            
    if row: # leftover
        buttons.append(row)
        
    # Audio button
    buttons.append([InlineKeyboardButton(text='🎤 Только звук', callback_data="yt_quality_audio")])
    
    # Cancel button
    buttons.append([InlineKeyboardButton(text='❌ Отмена', callback_data='download_cancel')])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)