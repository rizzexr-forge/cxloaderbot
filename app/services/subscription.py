import json
import os
import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

PARTNERS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'partners.json')

def load_partners():
    if not os.path.exists(PARTNERS_FILE):
        return {"watermark": "@rizzexr", "channels": []}
    try:
        with open(PARTNERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        logging.error(f"Error loading partners.json: {e}")
        return {"watermark": "@rizzexr", "channels": []}

def get_watermark():
    data = load_partners()
    return data.get("watermark", "@rizzexr")

async def get_unsubscribed_channels(bot: Bot, user_id: int):
    data = load_partners()
    channels: list[dict] = data.get("channels", [])
    if not channels:
        return []
    
    unsubscribed = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel['id'], user_id=user_id)
            if member.status in ['left', 'kicked', 'restricted']:
                unsubscribed.append(channel)
        except Exception as e:
            logging.error(f"Error checking subscription for {channel['id']}: {e}")
            unsubscribed.append(channel)
    return unsubscribed

def get_subscription_menu(unsubscribed_channels) -> InlineKeyboardMarkup:
    keyboard = []
    for channel in unsubscribed_channels:
        keyboard.append([InlineKeyboardButton(text=channel.get('name', 'Подписаться'), url=channel.get('url', ''))])
    
    keyboard.append([InlineKeyboardButton(text='✅ Проверить подписку', callback_data='check_sub')])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
