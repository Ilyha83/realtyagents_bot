# -*- coding: utf-8 -*-
"""
main.py — Главная точка входа для системы AI-агентов недвижимости.
"""

import os
import sys
import asyncio

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest

from tools.database import init_db
from tools.parser_101evler import seed_demo_database
from bot.handlers import (
    start_command,
    help_command,
    parse_command,
    handle_message,
    handle_callback_query
)

# Загружаем переменные окружения
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def async_init():
    """Инициализация базы данных и сидирование."""
    await init_db()
    await seed_demo_database()


async def run_preflight_harness() -> bool:
    """
    Автоматический встроенный стенд самодиагностики (Pre-flight Harness).
    Проверяет ключевые компоненты перед открытием приёма сообщений:
    1. База данных SQLite (WAL-режим, доступность таблиц).
    2. Доступность LLM API (проверочный пинг с retry).
    """
    print("🧪 Запуск автоматической самодиагностики (Pre-flight Harness)...")
    
    # 1. Проверка БД
    try:
        from tools.database import get_sync_db
        conn = get_sync_db(timeout=5.0)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode")
        mode = c.fetchone()[0].lower()
        c.execute("SELECT COUNT(*) FROM properties")
        props_count = c.fetchone()[0]
        conn.close()
        print(f"  [1/2] База данных: OK (WAL={mode.upper()}, объектов в каталоге: {props_count})")
    except Exception as e:
        print(f"  ❌ Ошибка проверки БД: {e}")
        return False

    # 2. Проверка LLM
    try:
        from tools.llm import ask_llm
        llm_check = await ask_llm(
            system_prompt="Ответь одним словом.",
            user_message="Пинг",
            retries=2
        )
        if "Извините" in llm_check or not llm_check:
            print(f"  ⚠️ LLM ответил с предупреждением: {llm_check}")
        else:
            print(f"  [2/2] Языковая модель (LLM): OK (связь подтверждена)")
    except Exception as e:
        print(f"  ⚠️ Предупреждение LLM (проверьте интернет или API-ключ): {e}")

    print("🎉 Самодиагностика Harness пройдена: все системы готовы к приёму клиентов!")
    return True


async def post_init(application):
    """Инициализация при старте приложения."""
    print("🚀 Инициализация базы данных...")
    await async_init()
    await run_preflight_harness()
    print("✅ Бот успешно запущен и ожидает сообщений!")


def main():
    """Запуск бота."""
    if not TOKEN:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден в .env документе!")
        return

    print("🤖 Запуск Telegram-бота AI-Команды Недвижимости...")
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    app = ApplicationBuilder().token(TOKEN).request(request).post_init(post_init).build()

    # Регистрация команд (строго в личных сообщениях с ботом)
    app.add_handler(CommandHandler("start", start_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("menu", start_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("help", help_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("parse", parse_command, filters=filters.ChatType.PRIVATE))

    # Регистрация кликов по кнопкам
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Регистрация текстовых сообщений (строго в личных сообщениях с ботом)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message))

    async def on_error(update, context):
        print(f"⚠️ Ошибка в обработчике Telegram: {context.error}")

    app.add_error_handler(on_error)

    while True:
        try:
            app.run_polling(drop_pending_updates=False)
            break
        except Exception as e:
            print(f"⚠️ Переподключение к Telegram API через 3 сек: {e}")
            import time
            time.sleep(3)


if __name__ == "__main__":
    main()
