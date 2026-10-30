"""
keyboards/inline.py — all inline (above-the-message) keyboards in one place.

A Mini App launch button is an InlineKeyboardButton with a `web_app`
payload (WebAppInfo) instead of `callback_data`/`url`. When the pupil
taps it, Telegram opens your HTTPS-hosted React app inside Telegram.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def main_menu_keyboard(mini_app_url: str) -> InlineKeyboardMarkup:
    """The home menu shown after /start."""
    open_app_btn = InlineKeyboardButton(
        text="🚀 O‘rganishni boshlash",
        web_app=WebAppInfo(url=mini_app_url),
    )
    return InlineKeyboardMarkup(inline_keyboard=[[open_app_btn]])
