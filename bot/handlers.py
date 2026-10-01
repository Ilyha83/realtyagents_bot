# -*- coding: utf-8 -*-
"""
handlers.py — Обработчики команд и сообщений Telegram-бота.
"""

import os
import html
import json
import re
import io
import urllib.request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from tools.database import get_or_create_client, update_client, search_properties, get_property_by_id, get_sync_db
from tools.parser_101evler import fetch_101evler_listings
from agents.coordinator import classify_intent
from agents.lead_manager import handle_lead, get_next_qualification_question
from agents.property_matcher import find_properties
from agents.market_analyst import (
    analyze_market,
    get_macro_period_report,
)
from agents.content_creator import create_social_post
from bot.keyboards import (
    get_main_keyboard,
    get_cities_keyboard,
    get_property_types_keyboard,
    get_deal_types_keyboard,
    get_analytics_periods_keyboard,
    get_analytics_back_keyboard,
    get_property_card_keyboard,
    get_search_results_keyboard,
    get_contact_manager_keyboard,
)

# Глобальный сессионный кэш для выбора объектов
LAST_SEARCH_RESULTS = {}  # {user_id: [property_ids]}
LAST_VIEWED = {}          # {user_id: property_id}


async def notify_managers(bot, text: str, parse_mode: str = "HTML"):
    """Отправляет служебное уведомление всем менеджерам/администраторам."""
    manager_ids_str = os.getenv("MANAGER_CHAT_IDS", "759218984,6881547934")
    ids = [int(i.strip()) for i in manager_ids_str.split(",") if i.strip().isdigit()]
    for mid in ids:
        try:
            await bot.send_message(chat_id=mid, text=text, parse_mode=parse_mode, disable_web_page_preview=True)
        except Exception as e:
            # При ошибках парсинга разметки отправляем без форматирования
            try:
                clean_text = re.sub(r'<[^>]+>', '', text)
                await bot.send_message(chat_id=mid, text=clean_text, disable_web_page_preview=True)
            except Exception as e2:
                print(f"⚠️ Не удалось отправить уведомление менеджеру {mid}: {e2}")


def get_user_search_results(user_id: int, client: dict = None) -> list:
    """Возвращает список ID объектов из последней подборки пользователя (из памяти или базы)."""
    ids = LAST_SEARCH_RESULTS.get(user_id)
    if ids:
        return ids
    if client and client.get("notes"):
        try:
            data = json.loads(client["notes"])
            if isinstance(data, dict) and "last_search" in data:
                LAST_SEARCH_RESULTS[user_id] = data["last_search"]
                return data["last_search"]
            elif isinstance(data, list):
                LAST_SEARCH_RESULTS[user_id] = data
                return data
        except Exception:
            pass
    return []

from tools.dates import extract_booking_dates


def clean_property_description(desc: str) -> str:
    """Очищает описание объекта от технических тегов каналов, ссылок и кнопок."""
    if not desc:
        return "Нет описания"
    lines = []
    for line in desc.split("\n"):
        line_clean = line.strip()
        # Пропускаем строки с хэштегами #id...
        if re.search(r'#\s*id[_\s]*\d+', line_clean, re.I):
            continue
        # Пропускаем кнопки и призывы подробнее / связаться / источник
        if re.search(r'(?:подробнее|связаться|источник|канал|чат|перейти|написать|контакт)\b', line_clean, re.I):
            continue
        if any(w in line_clean for w in ["ПОДРОБНЕЕ", "СВЯЗАТЬСЯ", "ИСТОЧНИК", "КАНАЛ"]):
            continue
        if "t.me/" in line_clean or "telegram.me/" in line_clean or "http://" in line_clean or "https://" in line_clean:
            continue
        if re.search(r'@\w+', line_clean):
            continue
        lines.append(line)
    text = "\n".join(lines).strip()
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'#\s*id[_\s]*\d+', '', text, flags=re.I)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() or "Нет описания"


def format_property_detail_card(p: dict) -> tuple[str, int]:
    """Форматирует подробную карточку объекта без внешних ссылок."""
    title = p.get('title', 'Объект недвижимости')
    city = p.get('city', 'Северный Кипр')
    district = p.get('district', '')
    loc = f"{district}, {city}" if district else city
    price = p.get('price', 0)
    curr = p.get('currency', 'GBP')
    curr_sym = '€' if curr == 'EUR' else ('£' if curr == 'GBP' else '$')
    ppd = p.get('price_per_day')
    desc = clean_property_description(p.get('description', 'Нет описания'))
    if p.get('listing_type') == 'rent':
        if ppd:
            price_str = f"{ppd:,.0f} {curr_sym}/сутки"
        elif price and price <= 400 and ('сутки' in desc.lower() or 'посуточн' in desc.lower()):
            price_str = f"{price:,.0f} {curr_sym}/сутки"
        else:
            price_str = f"{price:,.0f} {curr_sym}/месяц"
    else:
        price_str = f"£{price:,.0f}" if curr == 'GBP' else f"{price:,.0f} {curr}"
    bedrooms = p.get('bedrooms', 1)
    area = p.get('area_m2')
    area_str = f"{area} м²" if area else "Не указана"
    prop_id = p.get('id')

    detail_text = (
        f"🏠 **{title}**\n\n"
        f"📍 **Локация**: {loc}\n"
        f"💰 **Цена**: {price_str}\n"
        f"🛏 **Спальни**: {bedrooms}\n"
        f"📐 **Площадь**: {area_str}\n\n"
        f"📝 **Описание**:\n{desc}"
    )
    return detail_text, prop_id

PHOTO_BYTES_CACHE: dict[int, bytes] = {}

async def get_property_photo_bytes(p: dict) -> bytes | None:
    """Загружает реальные байты фото объекта (с CDN Telegram или базы) без ссылок на группы."""
    prop_id = p.get('id')
    if prop_id in PHOTO_BYTES_CACHE:
        return PHOTO_BYTES_CACHE[prop_id]

    source_url = p.get('source_url', '')
    if source_url and 't.me/' in source_url:
        clean_url = source_url.replace("https://t.me/", "https://t.me/s/")
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            def _fetch_img():
                req = urllib.request.Request(clean_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    html = resp.read().decode('utf-8', errors='ignore')
                    og = re.findall(r'<meta property="og:image" content="([^"]+)"', html)
                    if not og:
                        return None
                    img_req = urllib.request.Request(og[0], headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
                    with urllib.request.urlopen(img_req, timeout=6) as img_resp:
                        return img_resp.read()
            img_bytes = await loop.run_in_executor(None, _fetch_img)
            if img_bytes:
                PHOTO_BYTES_CACHE[prop_id] = img_bytes
                return img_bytes
        except Exception as e:
            print(f"⚠️ Ошибка загрузки фото для объекта {prop_id}: {e}")

    # Fallback на сохраненные в базе ссылки на фото
    photos = p.get('photos')
    if photos:
        try:
            p_list = json.loads(photos) if isinstance(photos, str) else photos
            if p_list and isinstance(p_list, list) and p_list[0] and 'unsplash' not in p_list[0]:
                import asyncio
                loop = asyncio.get_running_loop()
                def _download_url():
                    req = urllib.request.Request(p_list[0], headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        return resp.read()
                img_bytes = await loop.run_in_executor(None, _download_url)
                if img_bytes:
                    PHOTO_BYTES_CACHE[prop_id] = img_bytes
                    return img_bytes
        except Exception:
            pass

    return None


PROPERTY_ALBUM_MAP = {}

def load_property_album_map():
    """Рассчитывает точные границы фотоальбома каждого объекта, чтобы не захватывать соседние публикации."""
    global PROPERTY_ALBUM_MAP
    try:
        from collections import defaultdict
        conn = get_sync_db()
        c = conn.cursor()
        c.execute('SELECT id, source_url FROM properties WHERE source_url IS NOT NULL')
        rows = c.fetchall()
        groups = defaultdict(list)
        prop_info = {}
        for pid, url in rows:
            m = re.search(r't\.me/([^/]+)/(?:(\d+)/)?(\d+)', url)
            if m:
                channel = m.group(1)
                topic = int(m.group(2)) if m.group(2) else None
                msg_id = int(m.group(3))
                groups[(channel, topic)].append((pid, msg_id))
                prop_info[pid] = (channel, topic, msg_id)
        
        album_sizes = {}
        for key, items in groups.items():
            items.sort(key=lambda x: x[1])
            for i in range(len(items)):
                pid, mid = items[i]
                if i + 1 < len(items):
                    diff = items[i+1][1] - mid
                    size = min(10, max(1, diff))
                else:
                    size = 10
                album_sizes[pid] = (prop_info[pid][0], prop_info[pid][1], mid, size)
        PROPERTY_ALBUM_MAP = album_sizes
        conn.close()
    except Exception as e:
        print(f"⚠️ Ошибка построения карты альбомов: {e}")


async def send_property_card(target, p: dict, reply_markup, context=None):
    """
    Отправляет карточку объекта:
    1. Если бот добавлен в канал-источник — через copy_messages/copy_message
       (100% аналог "Переслать со скрытием автора" со ВСЕМИ оригинальными HD фото и текстом).
    2. Иначе — отправляет сохраненное фото и полный текст объявления с кнопками связи.
    """
    source_url = p.get('source_url', '')
    prop_id = p.get('id')

    if not PROPERTY_ALBUM_MAP:
        load_property_album_map()

    # Попытка прямого копирования альбома или сообщения без имени автора
    if source_url and 't.me/' in source_url and context:
        m = re.search(r't\.me/([^/]+)/(?:(\d+)/)?(\d+)', source_url)
        if m:
            channel_name = m.group(1)
            msg_id = int(m.group(3))
            from_chat = f"@{channel_name}"
            chat_id = target.chat.id if hasattr(target, 'chat') and target.chat else getattr(target, 'chat_id', None)
            if chat_id:
                album_info = PROPERTY_ALBUM_MAP.get(prop_id)
                target_size = album_info[3] if album_info else 10

                album_copied = False
                clean_desc = clean_property_description(p.get('description', ''))
                if len(clean_desc) > 1024:
                    clean_desc = clean_desc[:1020] + "..."

                # 1. Если в публикации больше 1 фото — отправляем альбом фото без чужих ссылок, а следом полную карточку с описанием и кнопками
                if target_size > 1:
                    for album_len in range(target_size, 1, -1):
                        album_ids = list(range(msg_id, msg_id + album_len))
                        try:
                            msgs = await context.bot.copy_messages(
                                chat_id=chat_id,
                                from_chat_id=from_chat,
                                message_ids=album_ids,
                                remove_caption=True
                            )
                            if msgs:
                                album_copied = True
                                detail_text, pid = format_property_detail_card(p)
                                card_msg = f"{detail_text}\n\n💬 _Свяжитесь с менеджером для консультации:_"
                                await safe_reply(
                                    target,
                                    card_msg,
                                    parse_mode="Markdown",
                                    reply_markup=reply_markup,
                                    disable_web_page_preview=True
                                )
                                return msgs
                        except Exception:
                            continue

                # 2. Если одиночный пост (1 фото) или copy_messages не прошел — копируем как одиночный пост с чистой подписью
                if not album_copied:
                    try:
                        copied = await context.bot.copy_message(
                            chat_id=chat_id,
                            from_chat_id=from_chat,
                            message_id=msg_id,
                            caption=clean_desc,
                            reply_markup=reply_markup
                        )
                        if copied:
                            return copied
                    except Exception as e:
                        print(f"ℹ️ copy_message не удался ({e}), используем прямую отправку фото-карточки")

    detail_text, pid = format_property_detail_card(p)
    img_bytes = await get_property_photo_bytes(p)

    if img_bytes:
        bio = io.BytesIO(img_bytes)
        bio.name = f"prop_{pid}.jpg"

        if len(detail_text) <= 1024:
            try:
                return await target.reply_photo(
                    photo=bio,
                    caption=detail_text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
            except Exception as e:
                print(f"⚠️ Ошибка отправки фото с подписью {pid}: {e}")
        else:
            # Описание длиннее 1024 символов: отправляем фото, а затем полный исходный текст без обрезки!
            try:
                bio.seek(0)
                await target.reply_photo(photo=bio)
                return await safe_reply(
                    target,
                    detail_text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            except Exception as e:
                print(f"⚠️ Ошибка раздельной отправки фото {pid}: {e}")

    # Fallback на аккуратное текстовое сообщение без фото
    return await safe_reply(
        target,
        detail_text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

async def safe_reply(target, text: str, **kwargs):
    """
    Безопасная отправка сообщения.
    При ошибках парсинга сущностей Markdown автоматически отправляет чистый текст.
    При кратковременных сетевых сбоях делает автоматический повтор.
    """
    for attempt in range(2):
        try:
            return await target.reply_text(text, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if "can't parse entities" in err_str or "badrequest" in type(e).__name__.lower():
                kwargs.pop("parse_mode", None)
                return await target.reply_text(text, **kwargs)
            if attempt == 0 and any(k in err_str for k in ["connect", "timed out", "network", "reset"]):
                import asyncio
                await asyncio.sleep(1.0)
                continue
            raise


async def safe_edit_message(query, text: str, reply_markup=None):
    """
    Безопасное редактирование сообщения callback-запроса.
    Сначала пробует HTML, при ошибке парсинга сущностей отправляет чистый текст.
    """
    try:
        return await query.edit_message_text(
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        err_str = str(e).lower()
        clean_text = re.sub(r'<[^>]+>', '', text)
        print(f"⚠️ safe_edit_message error: {e}, falling back to plain text")
        try:
            return await query.edit_message_text(
                text=clean_text,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        except Exception as e2:
            print(f"⚠️ safe_edit_message fallback error: {e2}, sending new message")
            return await query.message.reply_text(
                text=clean_text,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    user = update.effective_user

    # Полный сброс профиля и сессии при /start для чистого начала диалога
    await update_client(
        telegram_id=user.id,
        preferred_city=None,
        preferred_type=None,
        listing_type=None,
        budget_min=None,
        budget_max=None,
        bedrooms_min=None,
        booking_start_date=None,
        booking_end_date=None,
        status="new"
    )
    if user.id in LAST_SEARCH_RESULTS:
        del LAST_SEARCH_RESULTS[user.id]
    if user.id in LAST_VIEWED:
        del LAST_VIEWED[user.id]
    from agents.lead_manager import _conversations
    if user.id in _conversations:
        del _conversations[user.id]

    client = await get_or_create_client(telegram_id=user.id, name=user.full_name)

    welcome_text = (
        f"👋 **Здравствуйте, {user.first_name}!**\n\n"
        "Я — ваш интеллектуальный ассистент и команда AI-агентов по недвижимости **Северного Кипра** 🇨🇾\n\n"
        "**Чем моя команда может помочь?**\n"
        "• 📋 **Лид-Менеджер:** Подберёт идеальный вариант под ваш бюджет и пожелания\n"
        "• 🏘 **Подборщик:** Найдёт лучшие квартиры, виллы и пентхаусы в Кирении, Искеле и Фамагусте\n"
        "• 📊 **Аналитик:** Предоставит средние цены и аналитику рынка\n"
        "• ✍️ **Контент-Мейкер:** Составит привлекательное объявление или пост\n\n"
        "Просто напишите в чат, что вас интересует, например:\n"
        "_«Ищу виллу в Кирении до 300 000 фунтов»_ или нажмите одну из кнопок ниже 👇"
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    help_text = (
        "💡 **Инструкция по работе с AI-Командой:**\n\n"
        "1. **Поиск объектов:** Напишите параметры (город, спальни, бюджет)\n"
        "2. **Анализ рынка:** Запросите статистику цен по любому району\n"
        "3. **Обновление базы:** Используйте /parse для проверки новых объектов\n\n"
        "Доступные команды:\n"
        "/start — Перезапуск бота\n"
        "/help — Справка\n"
        "/parse — Обновить базу объектов с 101evler.com"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def parse_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /parse — ручной запуск обновления базы."""
    if not update.effective_chat or update.effective_chat.type != "private":
        return
    msg = await update.message.reply_text("🔄 Запущен поиск новых объектов на 101evler.com...")
    await fetch_101evler_listings()
    await msg.edit_text("✅ База данных объектов успешно обновлена и готова к работе!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главный обработчик входящих текстовых сообщений."""
    if not update.message or not update.effective_chat or update.effective_chat.type != "private":
        return
    user_text = (update.message.text or update.message.caption or "").strip()
    if not user_text:
        return
    user = update.effective_user

    # 1. Получаем данные клиента из БД
    client = await get_or_create_client(telegram_id=user.id, name=user.full_name)


    # Быстрая обработка нажатий основных кнопок меню
    if user_text == "🏠 Подобрать недвижимость":
        await update_client(
            user.id,
            preferred_type=None,
            listing_type=None,
            preferred_city=None,
            bedrooms_min=None,
            budget_min=None,
            budget_max=None,
            booking_start_date=None,
            booking_end_date=None,
            status="new"
        )
        await update.message.reply_text("Выберите интересующий регион:", reply_markup=get_cities_keyboard())
        return
    elif user_text == "📊 Аналитика рынка":
        intro_text = (
            "📊 <b>МАКРО-АНАЛИТИКА РЫНКА СЕВЕРНОГО КИПРА</b>\n"
            "<i>Агрегированные данные мониторинга Telegram-каналов и чатов от @NCyp_query_bot (7,360+ предложений с мая 2026)</i>\n\n"
            "Выберите интересующий период или раздел для просмотра динамики цен, регионального среза и юридических условий:"
        )
        await safe_reply(update.message, intro_text, parse_mode="HTML", reply_markup=get_analytics_periods_keyboard())
        return
    elif user_text.lower() in ["главное меню", "/menu", "меню", "в главное меню", "отмена", "start", "/start"]:
        await update_client(
            user.id,
            preferred_type=None,
            listing_type=None,
            preferred_city=None,
            bedrooms_min=None,
            bedrooms_max=None,
            budget_min=None,
            budget_max=None,
            booking_start_date=None,
            booking_end_date=None,
            status="new"
        )
        if user.id in LAST_SEARCH_RESULTS:
            del LAST_SEARCH_RESULTS[user.id]
        if user.id in LAST_VIEWED:
            del LAST_VIEWED[user.id]
        from agents.lead_manager import _conversations
        if user.id in _conversations:
            del _conversations[user.id]

        welcome_text = (
            f"👋 **Главное меню**\n\n"
            "Чем команда AI-агентов может помочь вам сегодня?\n\n"
            "• 🏠 **Подобрать недвижимость** — квартиры, виллы, пентхаусы в аренду и покупку\n"
            "• 📊 **Аналитика рынка** — средние цены, динамика, налоги и условия ВНЖ\n"
            "• 💬 **Свободный запрос** — просто напишите ваш вопрос или пожелания в чат"
        )
        await update.message.reply_text(
            welcome_text,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return

    # Обработка выбора объекта (цифра или фразы "можно подробнее?", "подробнее", "покажи", "расскажи")
    clean_text = user_text.strip().lower()
    target_idx = None

    # Если клиент в процессе квалификации (еще не собраны ключевые данные),
    # одиночные цифры ("1", "2") — это ответы на вопросы анкеты (число гостей/спален), а не выбор карточки!
    is_qualifying = (
        not client.get('listing_type') or
        (client.get('listing_type') == 'rent' and (not client.get('booking_start_date') or client.get('bedrooms_min') is None)) or
        (client.get('listing_type') == 'sale' and (not client.get('preferred_type') or client.get('bedrooms_min') is None))
    )

    if not is_qualifying:
        if clean_text.isdigit():
            target_idx = int(clean_text)
        elif user.id in LAST_SEARCH_RESULTS and LAST_SEARCH_RESULTS[user.id]:
            detail_triggers = ["подробн", "описани", "покажи", "расскажи", "детали", "фото", "первый", "второй", "третий"]
            if any(t in clean_text for t in detail_triggers):
                if "втор" in clean_text or "2" in clean_text:
                    target_idx = 2
                elif "трет" in clean_text or "3" in clean_text:
                    target_idx = 3
                else:
                    target_idx = 1

    if target_idx is not None and user.id in LAST_SEARCH_RESULTS:
        if 0 < target_idx <= len(LAST_SEARCH_RESULTS[user.id]):
            prop_id = LAST_SEARCH_RESULTS[user.id][target_idx - 1]
            LAST_VIEWED[user.id] = prop_id
            
            p = await get_property_by_id(prop_id)
            if p:
                await send_property_card(
                    update.message,
                    p,
                    reply_markup=get_property_card_keyboard(prop_id),
                    context=context
                )
                return

    # 2. Обработка отправки номера телефона
    clean_digits = re.sub(r'[^\d+]', '', user_text)
    if len(re.findall(r'\d', clean_digits)) >= 10 and not any(w in clean_text for w in ["до", "от", "евро", "долл", "фунт", "eur", "gbp"]):
        await update_client(telegram_id=user.id, phone=user_text.strip(), status="phone_received")
        username_str = f" (@{user.username})" if user.username else ""
        try:
            alert_text = (
                f"📞 <b>Получен телефон клиента!</b>\n\n"
                f"• <b>Клиент</b>: {user.full_name or 'Не указано'}{username_str}\n"
                f"• <b>Телефон</b>: <code>{user_text.strip()}</code>\n"
                f"• <b>ID</b>: <code>{user.id}</code>\n"
            )
            await notify_managers(context.bot, alert_text)
        except Exception as e:
            print(f"⚠️ Ошибка отправки уведомления о телефоне: {e}")

        await safe_reply(
            update.message,
            f"✅ <b>Спасибо! Ваш контакт принят.</b>\n\n"
            f"Наш старший менеджер свяжется с вами в течение 10–15 минут для подробной консультации.",
            parse_mode="HTML"
        )
        return

    # 3. Обработка запроса связи с живым человеком / менеджером / риелтором
    def _is_human_request(text: str) -> bool:
        t = text.lower().strip()
        # Исключаем вопросы об имени, личности, стоимости или отказы от риелтора
        if any(q in t for q in ["как зовут", "кто так", "кто он", "кто вы", "кто ты", "как его", "как вас", "сколько", "почему", "не нуж", "без риелтор", "без менеджер"]):
            return False
        connect_verbs = ["позови", "позовите", "дай", "дайте", "соедини", "соедините", "переключи", "переключите", "свяжи", "свяжите", "связаться с", "поговорить с", "пообщаться с", "нужен", "хочу", "передайте"]
        roles = ["человек", "менеджер", "риелтор", "риэлтор", "оператор", "специалист", "сотрудник"]
        for role in roles:
            if any(f"{v} {role}" in t or f"{v} с {role}" in t or f"{v} живого" in t for v in connect_verbs):
                return True
        direct_actions = [
            "позвони мне", "позвоните мне", "перезвони", "перезвоните", "наберите мне",
            "свяжитесь со мной", "свяжись со мной", "позвонить мне"
        ]
        if any(a in t for a in direct_actions):
            return True
        standalone = ["человека", "менеджера", "риелтора", "оператора", "живой человек", "живого человека", "оператор"]
        if t in standalone:
            return True
        return False

    if _is_human_request(clean_text):
        await update_client(telegram_id=user.id, status="manager_requested")
        username_str = f" (@{user.username})" if user.username else ""
        try:
            alert_text = (
                f"🚨 <b>Запрос связи с живым менеджером!</b>\n\n"
                f"• <b>Клиент</b>: {user.full_name or 'Не указано'}{username_str}\n"
                f"• <b>ID</b>: <code>{user.id}</code>\n"
                f"• <b>Запрос</b>: {user_text}\n"
            )
            await notify_managers(context.bot, alert_text)
        except Exception as e:
            print(f"⚠️ Ошибка отправки уведомления о менеджере: {e}")

        reply = (
            f"🤝 <b>Конечно! Я уже передал информацию нашему старшему менеджеру.</b>\n\n"
            f"Он напишет вам в Telegram{html.escape(username_str)} в ближайшее время.\n\n"
            f"📞 Если вам удобнее обсудить всё по телефону или в WhatsApp, напишите ваш номер телефона, и менеджер сразу вам перезвонит!"
        )
        await safe_reply(update.message, reply, parse_mode="HTML")
        return

    # 4. Обработка прощаний, благодарностей и коротких подтверждений
    # ВНИМАНИЕ: исключаем запросы по недвижимости, чтобы не путать "покупка" (где есть 'ок') или "покажи" (где есть 'пока')!
    is_real_estate_text = any(k in clean_text for k in [
        "покуп", "куп", "аренд", "сним", "сутк", "квартир", "вилл", "студи",
        "искеле", "кирени", "фамагуст", "евро", "фунт", "тысяч", "1+", "2+", "3+",
        "вариант", "найди", "покажи", "что есть", "подбор"
    ])

    farewell_phrases = [
        "до свидания", "до встречи", "до связи", "хорошего дня", "всего доброго",
        "ок, спасибо", "ок спасибо", "спасибо большое", "буду ждать", "все понял"
    ]
    words_in_text = set(re.findall(r'[a-zа-яё0-9]+', clean_text))
    single_farewell_words = {"спасибо", "благодарю", "договорились", "понятно", "ясно", "ок", "ладно"}

    is_farewell = False
    if not is_real_estate_text:
        if any(p in clean_text for p in farewell_phrases):
            is_farewell = True
        elif words_in_text and words_in_text.issubset(single_farewell_words | {"да", "хорошо"}):
            is_farewell = True

    if is_farewell:
        if client.get('status') in ['manager_requested', 'phone_received']:
            await update.message.reply_text("🤝 Договорились! Менеджер уже подключается к диалогу.", parse_mode="Markdown")
        elif client.get('status') == 'qualified':
            await update.message.reply_text("Рад был помочь! 🤝 Наш старший риелтор свяжется с вами в ближайшее время для организации просмотра. Если возникнут любые вопросы или захотите посмотреть другие варианты — просто напишите сюда! Хорошего дня! 😊", parse_mode="Markdown")
        else:
            await update.message.reply_text("Пожалуйста! Всегда рад помочь. Обращайтесь в любое время! 😊", parse_mode="Markdown")
        return

    # 4.5. Перехват выбора объекта по номеру из ранее показанной подборки ("1", "2", "3", "4", "вариант 4" и т.д.)
    raw_user_num = None
    clean_low = user_text.lower().strip()
    m_var = re.match(r'^(?:(?:вариант|объект|номер|вар\.?|№|#)\s*)?([1-9])(?:\s*(?:подробнее|покажи|открой|вариант))?$', clean_low)
    if m_var:
        raw_user_num = int(m_var.group(1))
    elif clean_low in ["первый", "1-й", "1й"]:
        raw_user_num = 1
    elif clean_low in ["второй", "2-й", "2й"]:
        raw_user_num = 2
    elif clean_low in ["третий", "3-й", "3й"]:
        raw_user_num = 3
    elif clean_low in ["четвертый", "четвёртый", "4-й", "4й"]:
        raw_user_num = 4

    cached_ids = get_user_search_results(user.id, client)
    if cached_ids and raw_user_num and 1 <= raw_user_num <= len(cached_ids):
        target_pid = cached_ids[raw_user_num - 1]
        p = await get_property_by_id(target_pid)
        if p:
            LAST_VIEWED[user.id] = target_pid
            await send_property_card(
                update.message,
                p,
                reply_markup=get_property_card_keyboard(target_pid),
                context=context
            )
            return

    # 5. Роутинг через Координатор
    status_msg = None

    try:
        classification = await classify_intent(user_text)
        intent = classification.get("intent")
        params = classification.get("params", {})

        # Детерминированное извлечение и валидация параметров в Python
        text_low = user_text.lower()
        step_before, _ = get_next_qualification_question(client)

        new_inquiry_words = ["нужна", "ищу", "хочу", "подберите", "подобрать", "подыщи", "найти", "покажи что", "какие есть варианты"]
        is_fresh_inquiry = any(w in text_low for w in new_inquiry_words) or client.get('status') == 'qualified'

        # 1. Тип сделки
        rent_keywords = [
            "аренд", "сним", "снять", "посут", "сутк", "суточ", "пожит", "пожив",
            "недел", "недельк", "попробовать пожить", "остановит", "отпуск", "rent"
        ]
        buy_keywords = ["куп", "покуп", "приобре", "инвест", "выкуп", "buy", "sale"]
        has_rent = any(k in text_low for k in rent_keywords)
        has_buy = any(k in text_low for k in buy_keywords)

        if has_rent:
            params["listing_type"] = "rent"
        elif has_buy:
            params["listing_type"] = "sale"
        elif not params.get("listing_type"):
            pass
        elif not has_rent and not has_buy:
            params["listing_type"] = None

        # Суточный бюджет (< 1000 без слова тысяч) всегда указывает на аренду
        if params.get("budget_max") and params["budget_max"] < 1000 and not any(k in text_low for k in ["тыс", "тысяч", "к", "k"]):
            params["listing_type"] = "rent"

        # 2. Тип недвижимости: СТРОГО определяем только по наличию явных ключевых слов в тексте
        prop_type_words = {
            "villa": ["вилл", "villa", "коттедж", "таунхаус"],
            "penthouse": ["пентхаус", "penthouse"],
            "apartment": ["квартир", "апартамент", "apart", "flat"],
            "studio": ["студи", "studio"],
            "house": [" дом", "дома", "доме", "домик", "house"]
        }
        p_types = []
        for ptype, kws in prop_type_words.items():
            if any(w in text_low for w in kws):
                p_types.append(ptype)
        if p_types:
            params["property_type"] = ", ".join(p_types)
        else:
            params["property_type"] = None

        # 3. Город: СТРОГО только если название города присутствует в текущем тексте пользователя
        city_detected = None
        if any(w in text_low for w in ["кирени", "girne", "kyrenia", "гирне", "алсанджак", "лапта", "эсентепе"]):
            city_detected = "Кирения"
        elif any(w in text_low for w in ["искеле", "iskele", "long beach", "лонг бич", "боаз", "богаз"]):
            city_detected = "Искеле"
        elif any(w in text_low for w in ["фамагуст", "famagusta", "гасимагус", "magusa"]):
            city_detected = "Фамагуста"
        elif any(w in text_low for w in ["никоси", "nicosia", "лефкош", "lefkosa"]):
            city_detected = "Никосия"
        elif any(w in text_low for w in ["гюзел", "guzelyurt", "морфу", "morphou", "лефке", "lefke", "газиверен", "gaziveren"]):
            city_detected = "Гюзельюрт"

        if city_detected:
            params["city"] = city_detected
        elif params.get("city") and isinstance(params["city"], str) and params["city"].lower().strip() in ["null", "none", "undefined", ""]:
            params["city"] = None
        elif params.get("city") and not any(c_name in params["city"].lower() for c_name in ["кирен", "искел", "фамагуст", "никоси", "гюзел", "лефк", "газив"]):
            params["city"] = None

        # 4. Спальни / Гости
        has_dates = bool(params.get("booking_start_date") or any(mon in text_low for mon in ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек", "cент"]))
        has_explicit_beds = any(w in text_low for w in ["спал", "комнат", "+1", "1+0", "однушк", "двушк", "трешк", "студи", "человек", "гост", "семья", "вдвоем", "двое", "один", "пара"])

        if has_dates and not has_explicit_beds:
            params["bedrooms"] = None
            params["bedrooms_min"] = None
            params["bedrooms_max"] = None
            params["bedrooms_list"] = None
        else:
            current_deal = params.get("listing_type") or client.get("listing_type")
            if "1+1" in text_low or "однушк" in text_low or "1 спальн" in text_low:
                params["bedrooms"] = 1
            elif "2+1" in text_low or "двушк" in text_low or "2 спальн" in text_low:
                params["bedrooms"] = 2
            elif "3+1" in text_low or "трешк" in text_low or "3 спальн" in text_low:
                params["bedrooms"] = 3
            elif "4+1" in text_low or "4 спальн" in text_low:
                params["bedrooms"] = 4
            elif current_deal == "rent" or step_before == "bedrooms":
                # Для посуточной аренды вопрос: "сколько человек будет проживать (один, пара или семья с детьми)?"
                # Ответ "1" или "2" — это 1-2 ЧЕЛОВЕКА, для которых подходят 1-спальные апартаменты (1+1 или студия)
                if text_low.strip() in ["1", "2"] or any(w in text_low for w in ["один", "одна", "одного", "одной", "вдвоем", "вдвойне", "двое", "двоих", "паро", "пара", "паре", "пару", "с девушк", "с жен", "с муж", "на двоих", "на одного"]):
                    params["bedrooms"] = 1
                elif text_low.strip() in ["3", "4"] or any(w in text_low for w in ["трое", "троих", "на троих", "четвер", "четверых", "на четвер", "ребенк", "детьм", "семья с"]):
                    params["bedrooms"] = 2
                elif text_low.strip() in ["5", "6"] or any(w in text_low for w in ["пятер", "пятерых", "шестер", "компани"]):
                    params["bedrooms"] = 3
                elif re.search(r'\b([1-9])\s*(?:чел|гост|взросл|мест)', text_low):
                    m = re.search(r'\b([1-9])\s*(?:чел|гост|взросл|мест)', text_low)
                    n_people = int(m.group(1))
                    params["bedrooms"] = 1 if n_people <= 2 else (2 if n_people <= 4 else 3)
                elif text_low.strip().isdigit() and int(text_low.strip()) <= 5:
                    params["bedrooms"] = 1 if int(text_low.strip()) <= 2 else 2
            else:
                # Для покупки: число спален
                if text_low.strip() in ["1", "2", "3", "4", "5"]:
                    params["bedrooms"] = int(text_low.strip())
                elif any(w in text_low for w in ["один", "одна", "вдвоем", "двое", "пара", "на двоих"]):
                    params["bedrooms"] = 1
                elif any(w in text_low for w in ["трое", "троих", "семья с"]):
                    params["bedrooms"] = 2
                elif re.search(r'\b([1-9])\s*(?:спальн|комнат)', text_low):
                    m = re.search(r'\b([1-9])\s*(?:спальн|комнат)', text_low)
                    params["bedrooms"] = int(m.group(1))

        # 4.1 Проверяем указание на прежние даты ("те же даты", "прежние даты", "даты те же")
        same_dates_triggers = ["те же дат", "прежни", "как раньше", "как и раньше", "те же числ", "в те же дни", "на те же дни"]
        if any(sdt in text_low for sdt in same_dates_triggers):
            if client.get("booking_start_date") and client.get("booking_end_date"):
                params["booking_start_date"] = client["booking_start_date"]
                params["booking_end_date"] = client["booking_end_date"]
            else:
                try:
                    conn = get_sync_db()
                    c = conn.cursor()
                    c.execute("SELECT details FROM interactions WHERE client_id = ? ORDER BY id DESC LIMIT 30", (client.get('id', 0),))
                    rows = c.fetchall()
                    for r in rows:
                        m = re.search(r'User:\s*(\d{1,2}\s*[-–—]\s*\d{1,2}\s+[а-яА-Яa-zA-Z]+)', r[0])
                        if m:
                            past_date_str = m.group(1)
                            parsed = await classify_intent(past_date_str)
                            if parsed.get('params', {}).get('booking_start_date'):
                                params['booking_start_date'] = parsed['params']['booking_start_date']
                                params['booking_end_date'] = parsed['params']['booking_end_date']
                                break
                except Exception as e:
                    print(f"⚠️ Ошибка восстановления дат: {e}")

        # 4.2 Детерминированное извлечение дат из текущего сообщения пользователя (fallback, если LLM не распознал)
        if not params.get("booking_start_date"):
            b_s, b_e = extract_booking_dates(user_text)
            if b_s and b_e:
                params["booking_start_date"] = b_s
                params["booking_end_date"] = b_e

        # 5. Бюджет: детерминированное извлечение бюджета из текста
        t_clean = text_low.strip()
        if t_clean.isdigit() and int(t_clean) >= 20 and not (20 <= int(t_clean) <= 31 and any(mon in text_low for mon in ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"])):
            params["budget_max"] = float(t_clean)
        else:
            m1 = re.search(r'(?:до|около|бюджет\s*(?:до)?|тогда|пусть|ну|максимум)?\s*(\d+[\d\s]*)\s*(?:тыс|тысяч|[кk])?\s*(?:фунт|евро|eur|€|\$|долл|gbp|лир)?', text_low)
            if m1 and m1.group(1).strip():
                s = m1.group(1).replace(' ', '')
                if s.isdigit():
                    val = float(s)
                    if any(k in m1.group(0) for k in ['тыс', 'тысяч', 'к', 'k']):
                        val *= 1000
                    if val >= 20 and not (20 <= val <= 31 and any(mon in text_low for mon in ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"])):
                        params["budget_max"] = val
            elif any(w in text_low for w in ["любой", "без разниц", "не важно", "без огранич"]):
                params["budget_max"] = 999999

        update_data = {}

        # Сброс старых параметров предыдущей сессии при новом запросе или при переходе от шага сделки
        if is_fresh_inquiry or step_before == "listing_type":
            if not params.get("booking_start_date") and not any(sdt in text_low for sdt in same_dates_triggers):
                update_data["booking_start_date"] = None
                update_data["booking_end_date"] = None
                client["booking_start_date"] = None
                client["booking_end_date"] = None
            if not params.get("bedrooms") and params.get("bedrooms_min") is None:
                update_data["bedrooms_min"] = None
                update_data["bedrooms_max"] = None
                client["bedrooms_min"] = None
                client["bedrooms_max"] = None
            if not params.get("budget_max") and not params.get("budget_min"):
                update_data["budget_max"] = None
                update_data["budget_min"] = None
                client["budget_max"] = None
                client["budget_min"] = None
            update_data["status"] = "new"
            client["status"] = "new"

        # Обновляем профиль клиента извлечёнными параметрами
        if params.get("city"):
            update_data["preferred_city"] = params["city"]
        if params.get("property_type"):
            update_data["preferred_type"] = params["property_type"]
        if params.get("listing_type"):
            update_data["listing_type"] = params["listing_type"]
            if client.get("listing_type") and params["listing_type"] != client.get("listing_type"):
                # Только при реальной смене типа сделки (с покупки на аренду или наоборот)
                if not params.get("property_type"):
                    update_data["preferred_type"] = None
                update_data["budget_max"] = None
                update_data["budget_min"] = None
        if params.get("budget_min") is not None:
            update_data["budget_min"] = params["budget_min"]
        if params.get("budget_max") is not None:
            update_data["budget_max"] = params["budget_max"]
        if params.get("bedrooms_min") is not None:
            update_data["bedrooms_min"] = params["bedrooms_min"]
        if params.get("bedrooms_max") is not None:
            update_data["bedrooms_max"] = params["bedrooms_max"]
        elif params.get("bedrooms") is not None:
            if isinstance(params["bedrooms"], int):
                update_data["bedrooms_min"] = params["bedrooms"]
                update_data["bedrooms_max"] = params["bedrooms"]
            elif isinstance(params["bedrooms"], list) and params["bedrooms"]:
                update_data["bedrooms_min"] = min(params["bedrooms"])
                update_data["bedrooms_max"] = max(params["bedrooms"])
        if params.get("booking_start_date"):
            update_data["booking_start_date"] = params["booking_start_date"]
        if params.get("booking_end_date"):
            update_data["booking_end_date"] = params["booking_end_date"]

        if update_data:
            await update_client(telegram_id=user.id, **update_data)
            client = await get_or_create_client(telegram_id=user.id)

        # Объединяем накопленный контекст клиента и новые параметры
        current_listing_type = params.get("listing_type") or client.get("listing_type")
        raw_b_min = params.get("budget_min") if params.get("budget_min") is not None else client.get("budget_min")
        raw_b_max = params.get("budget_max") if params.get("budget_max") is not None else client.get("budget_max")
        
        # Защита от несовместимых бюджетов (арендный бюджет на покупку или бюджет покупки на аренду)
        if current_listing_type == "sale":
            b_min = raw_b_min if (raw_b_min and raw_b_min >= 10000) else None
            b_max = raw_b_max if (raw_b_max and raw_b_max >= 10000) else None
            b_start = None
            b_end = None
        else:
            b_min = raw_b_min if (raw_b_min and raw_b_min < 10000) else None
            b_max = raw_b_max if (raw_b_max and raw_b_max < 10000) else None
            b_start = params.get("booking_start_date") or client.get("booking_start_date")
            b_end = params.get("booking_end_date") or client.get("booking_end_date")

        b_min_val = params.get("bedrooms_min") if params.get("bedrooms_min") is not None else client.get("bedrooms_min")
        b_max_val = params.get("bedrooms_max") if params.get("bedrooms_max") is not None else client.get("bedrooms_max")
        if b_min_val is None and params.get("bedrooms") is not None:
            if isinstance(params["bedrooms"], int):
                b_min_val = params["bedrooms"]
                b_max_val = params["bedrooms"]
            elif isinstance(params["bedrooms"], list) and params["bedrooms"]:
                b_min_val = min(params["bedrooms"])
                b_max_val = max(params["bedrooms"])

        b_list_val = params.get("bedrooms_list")
        if not b_list_val and b_min_val is not None and b_max_val is not None:
            b_list_val = list(range(int(b_min_val), int(b_max_val) + 1))

        full_params = {
            "city": params.get("city") or client.get("preferred_city"),
            "property_type": params.get("property_type") or client.get("preferred_type"),
            "listing_type": current_listing_type,
            "budget_min": b_min,
            "budget_max": b_max,
            "bedrooms_min": b_min_val,
            "bedrooms_max": b_max_val,
            "bedrooms_list": b_list_val,
            "bedrooms": b_min_val,
            "booking_start_date": b_start,
            "booking_end_date": b_end,
        }

        # Проверяем, посуточная ли это аренда
        is_short_rent = False
        if full_params.get("listing_type") == "rent":
            if full_params.get("booking_start_date") and full_params.get("booking_end_date"):
                is_short_rent = True
            else:
                q_low = user_text.lower()
                short_term_keywords = ["посуточно", "сутки", "несколько дней", "день", "дни", "short term", "daily", "пожить неделю", "две недели", "отпуск", "остановиться"]
                if any(k in q_low for k in short_term_keywords):
                    is_short_rent = True

        # Проверяем стадию квалификации лида
        step_name, next_q = get_next_qualification_question(client)
        is_fully_qualified = (next_q is None)

        # Прямой поисковый запрос (например: "покажи варианты", "что есть в наличии")
        is_explicit_search = any(w in user_text.lower() for w in ["что есть", "какие есть", "покажи", "найди", "подбери", "вариант", "предложи", "список"])

        # Проверяем достаточность параметров для поиска:
        if full_params.get("listing_type") == "sale":
            has_enough_params = bool(full_params.get("city") and full_params.get("property_type") and (full_params.get("budget_max") or full_params.get("budget_min")))
        else:
            # Для аренды: обязательно город и даты (или принудительный поиск от клиента)
            has_enough_params = bool(full_params.get("city") and full_params.get("listing_type") and (full_params.get("booking_start_date") or is_explicit_search))

        # Если сообщение является вопросом о конкретном объекте, возмущением или уточнением — отправляем в Лид-Менеджер, а не спамим подборкой!
        is_clarification_question = "?" in user_text and any(w in text_low for w in ["это", "точно", "там", "есть ли", "вилла ли", "почему", "зачем"])
        is_question_or_protest = is_clarification_question or any(w in text_low for w in ["блять", "бля", "сука", "почему", "зачем", "это не", "а не", "не вилла", "не боаз", "кто"])

        # Выводим объекты только если клиент полностью квалифицирован или прямо требует ("покажи")
        should_search = (is_explicit_search or is_fully_qualified) and has_enough_params and not is_question_or_protest

        if should_search:
            status_msg = await safe_reply(update.message, "🔎 _Агент-подборщик ищет подходящие варианты в базе..._", parse_mode="Markdown")
            
            response, selected_ids = await find_properties(full_params, query=user_text)
            LAST_SEARCH_RESULTS[user.id] = selected_ids
            try:
                await update_client(telegram_id=user.id, notes=json.dumps({"last_search": selected_ids}))
            except Exception:
                pass
            await safe_reply(
                update.message,
                response,
                parse_mode="Markdown",
                reply_markup=get_search_results_keyboard(selected_ids),
                disable_web_page_preview=True
            )

        elif intent == "analytics":
            status_msg = await safe_reply(update.message, "📊 _Аналитик рынка обрабатывает финансовые показатели..._", parse_mode="Markdown")
            response = await analyze_market(user_text)
            await safe_reply(update.message, response, parse_mode="Markdown")

        elif intent == "content":
            status_msg = await safe_reply(update.message, "✍️ _Контент-мейкер создаёт продающее описание..._", parse_mode="Markdown")
            fake_prop = {"title": user_text, "description": user_text, "city": params.get("city", "Северный Кипр")}
            response = await create_social_post(fake_prop)
            await safe_reply(update.message, response, parse_mode="Markdown")

        else: # greeting, info, or incomplete search redirecting to lead manager
            response = await handle_lead(telegram_id=user.id, user_message=user_text, client_data=client)
            if "[READY]" in response:
                await update_client(telegram_id=user.id, status="qualified")
                
                # Отправка уведомления маклеру
                try:
                    # Подготавливаем сводку параметров лида
                    city_pref = client.get('preferred_city') or 'Не указан'
                    type_pref = client.get('preferred_type') or 'Не указан'
                    b_min = client.get('budget_min')
                    b_max = client.get('budget_max')
                    b_min_str = f"{b_min:,.0f}" if b_min is not None else "0"
                    b_max_str = f"{b_max:,.0f}" if b_max is not None else "..."
                    budget_str = f"{b_min_str} - {b_max_str}" if (b_min is not None or b_max is not None) else "Не указан"
                    
                    lead_summary = (
                        f"⚡️ <b>Новый горячий лид!</b>\n\n"
                        f"• <b>Имя</b>: {user.full_name or 'Не указано'}\n"
                        f"• <b>Telegram</b>: @{user.username or 'нет'}\n"
                        f"• <b>Предпочитаемый город</b>: {city_pref}\n"
                        f"• <b>Тип объекта</b>: {type_pref}\n"
                        f"• <b>Бюджет</b>: {budget_str}\n\n"
                        f"💬 <i>Диалог квалифицирован ассистентом. Лид готов к связи.</i>"
                    )
                    await notify_managers(context.bot, lead_summary)
                except Exception as e:
                    print(f"⚠️ Ошибка отправки уведомления маклеру: {e}")
                    
            # Очищаем технические маркеры
            clean_response = response.replace("[READY]", "").strip()
            # Экранируем спецсимволы в юзернейме маклера
            reply_markup = get_deal_types_keyboard() if "покупку недвижимости или аренду" in clean_response else None
            await safe_reply(update.message, clean_response, parse_mode="Markdown", reply_markup=reply_markup)
            
            # Если квалификация завершена, тут же выводим подборку клиенту
            if "[READY]" in response:
                client_full = await get_or_create_client(user.id)
                l_type = client_full.get("listing_type")
                if not l_type and (client_full.get("booking_start_date") or is_short_rent):
                    l_type = "rent"
                b_min_c = client_full.get("bedrooms_min")
                b_max_c = client_full.get("bedrooms_max")
                b_list_c = list(range(int(b_min_c), int(b_max_c) + 1)) if (b_min_c is not None and b_max_c is not None) else None
                search_params = {
                    "city": client_full.get("preferred_city"),
                    "property_type": client_full.get("preferred_type"),
                    "listing_type": l_type or "rent",
                    "budget_min": client_full.get("budget_min"),
                    "budget_max": client_full.get("budget_max"),
                    "bedrooms_min": b_min_c,
                    "bedrooms_max": b_max_c,
                    "bedrooms_list": b_list_c,
                    "bedrooms": b_min_c,
                    "booking_start_date": client_full.get("booking_start_date"),
                    "booking_end_date": client_full.get("booking_end_date"),
                }
                search_text, selected_ids = await find_properties(search_params, query=user_text)
                LAST_SEARCH_RESULTS[user.id] = selected_ids
                try:
                    await update_client(telegram_id=user.id, notes=json.dumps({"last_search": selected_ids}))
                except Exception:
                    pass
                await safe_reply(update.message, "✨ *Вот варианты из нашей базы под ваш запрос:*", parse_mode="Markdown")
                await safe_reply(
                    update.message,
                    search_text,
                    parse_mode="Markdown",
                    reply_markup=get_search_results_keyboard(selected_ids),
                    disable_web_page_preview=True
                )
    except Exception as e:
        print(f"[HANDLERS ERROR] {e}")
        try:
            await safe_reply(update.message, "Прошу прощения, произошла небольшая заминка. Пожалуйста, повторите запрос или напишите нашему старшему риелтору Илье (@makler_cy).")
        except Exception:
            pass
    finally:
        # Удаляем статусный маркер
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кликов по inline-кнопкам."""
    query = update.callback_query
    if not query or not update.effective_chat or update.effective_chat.type != "private":
        return
    await query.answer()

    data = query.data
    user = update.effective_user

    if data.startswith("city_"):
        city = data.split("city_")[1]
        reset_fields = {
            "preferred_type": None,
            "bedrooms_min": None,
            "bedrooms_max": None,
            "budget_min": None,
            "budget_max": None,
            "listing_type": None,
            "booking_start_date": None,
            "booking_end_date": None,
            "status": "new"
        }
        if city == "all":
            await update_client(user.id, preferred_city=None, **reset_fields)
            await query.edit_message_text("Показаны все регионы. Теперь выберите тип недвижимости:", reply_markup=get_property_types_keyboard())
        else:
            city_display = {
                "Kyrenia": "Кирения",
                "Iskele": "Искеле",
                "Famagusta": "Фамагуста",
                "Nicosia": "Никосия",
                "Guzelyurt": "Гюзельюрт (Лефке, Газиверен)"
            }.get(city, city)
            city_val = "Гюзельюрт" if city == "Guzelyurt" else city_display
            await update_client(user.id, preferred_city=city_val, **reset_fields)
            await query.edit_message_text(f"Выбран регион: **{city_display}**. Теперь выберите тип объекта:", parse_mode="Markdown", reply_markup=get_property_types_keyboard())

    elif data.startswith("type_"):
        prop_type = data.split("type_")[1]
        type_name = {"apartment": "квартира", "villa": "вилла", "penthouse": "пентхаус", "studio": "студия", "land": "участок"}.get(prop_type, prop_type)

        # 1. Обновляем тип объекта в профиле клиента
        await update_client(user.id, preferred_type=type_name if prop_type != "all" else None)
        client = await get_or_create_client(user.id)

        await query.edit_message_text("💬 _Лид-Менеджер обрабатывает параметры подбора..._", parse_mode="Markdown")
        
        # 2. Инициируем диалог квалификации с Лид-Менеджером
        user_message = f"[Выбран тип объекта: {type_name if prop_type != 'all' else 'Любой'}]"
        response = await handle_lead(telegram_id=user.id, user_message=user_message, client_data=client)
        
        # Очищаем технические маркеры
        clean_response = response.replace("[READY]", "").strip()
        reply_markup = get_deal_types_keyboard() if "покупку недвижимости или аренду" in clean_response else None
        await query.message.reply_text(clean_response, parse_mode="Markdown", reply_markup=reply_markup)

    elif data.startswith("deal_"):
        deal_type = data.split("deal_")[1]
        deal_name = "покупка" if deal_type == "sale" else "аренда"
        await update_client(user.id, listing_type=deal_type)
        client = await get_or_create_client(user.id)

        user_message = f"[Выбран тип сделки: {deal_name}]"
        response = await handle_lead(telegram_id=user.id, user_message=user_message, client_data=client)
        clean_response = response.replace("[READY]", "").strip()
        await query.message.reply_text(clean_response, parse_mode="Markdown")

    elif data.startswith("aperiod_"):
        period = data.replace("aperiod_", "")
        if period == "menu":
            intro_text = (
                "📊 <b>МАКРО-АНАЛИТИКА РЫНКА СЕВЕРНОГО КИПРА</b>\n"
                "<i>Агрегированные данные мониторинга Telegram-каналов и чатов от @NCyp_query_bot (7,360+ предложений с мая 2026)</i>\n\n"
                "Выберите интересующий период или раздел для просмотра динамики цен, регионального среза и юридических условий:"
            )
            await safe_edit_message(query, intro_text, reply_markup=get_analytics_periods_keyboard())
        else:
            report = get_macro_period_report(period)
            await safe_edit_message(query, report, reply_markup=get_analytics_back_keyboard())

    elif data == "back_to_cities":
        await query.edit_message_text("Выберите интересующий регион:", reply_markup=get_cities_keyboard())

    elif data == "restart_search":
        await update_client(
            user.id,
            preferred_type=None,
            listing_type=None,
            preferred_city=None,
            bedrooms_min=None,
            bedrooms_max=None,
            budget_min=None,
            budget_max=None,
            booking_start_date=None,
            booking_end_date=None,
            status="new"
        )
        if user.id in LAST_SEARCH_RESULTS:
            del LAST_SEARCH_RESULTS[user.id]
        if user.id in LAST_VIEWED:
            del LAST_VIEWED[user.id]
        from agents.lead_manager import _conversations
        if user.id in _conversations:
            del _conversations[user.id]

        await query.message.reply_text("Выберите интересующий регион:", reply_markup=get_cities_keyboard())

    elif data == "main_menu":
        await update_client(
            user.id,
            preferred_type=None,
            listing_type=None,
            preferred_city=None,
            bedrooms_min=None,
            bedrooms_max=None,
            budget_min=None,
            budget_max=None,
            booking_start_date=None,
            booking_end_date=None,
            status="new"
        )
        if user.id in LAST_SEARCH_RESULTS:
            del LAST_SEARCH_RESULTS[user.id]
        if user.id in LAST_VIEWED:
            del LAST_VIEWED[user.id]
        from agents.lead_manager import _conversations
        if user.id in _conversations:
            del _conversations[user.id]

        welcome_text = (
            f"👋 **Главное меню**\n\n"
            "Чем команда AI-агентов может помочь вам сегодня?\n\n"
            "• 🏠 **Подобрать недвижимость** — квартиры, виллы, пентхаусы в аренду и покупку\n"
            "• 📊 **Аналитика рынка** — средние цены, динамика, налоги и условия ВНЖ\n"
            "• 💬 **Свободный запрос** — просто напишите ваш вопрос или пожелания в чат"
        )
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text(
            welcome_text,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

    elif data == "back_to_search":
        client_data = await get_or_create_client(user.id)
        selected_ids = get_user_search_results(user.id, client_data)
        if selected_ids:
            items_text = []
            for idx, pid in enumerate(selected_ids[:4], 1):
                p = await get_property_by_id(pid)
                if p:
                    title = p.get('title', 'Объект недвижимости')
                    city = p.get('city', 'Северный Кипр')
                    price = p.get('price', 0)
                    curr = p.get('currency', 'GBP')
                    price_str = f"£{price:,.0f}" if curr == 'GBP' else f"{price:,.0f} {curr}"
                    bedrooms = p.get('bedrooms', 1)
                    num_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"][idx - 1]
                    items_text.append(f"{num_emoji} **{title}**\n📍 {city} | 🛏 {bedrooms} сп. | 💰 {price_str}")
            
            summary_msg = "✨ **Ваша подборка объектов:**\n\n" + "\n\n".join(items_text)
            summary_msg += "\n\n_Нажмите на номер объекта ниже или отправьте его номер в чат, чтобы открыть подробности:_"
            await query.message.reply_text(
                summary_msg,
                parse_mode="Markdown",
                reply_markup=get_search_results_keyboard(selected_ids),
                disable_web_page_preview=True
            )
        else:
            await query.message.reply_text(
                "📋 Нажмите кнопку ниже, чтобы начать новый подбор вариантов:",
                reply_markup=get_cities_keyboard()
            )

    elif data.startswith("prop_card_"):
        prop_id_str = data.split("prop_card_")[1]
        try:
            prop_id = int(prop_id_str)
            p = await get_property_by_id(prop_id)
            if p:
                LAST_VIEWED[user.id] = prop_id
                await send_property_card(
                    query.message,
                    p,
                    reply_markup=get_property_card_keyboard(prop_id),
                    context=context
                )
        except Exception as e:
            print(f"⚠️ Ошибка показа карточки {prop_id_str}: {e}")

    elif data.startswith("viewing_"):
        prop_id_str = data.split("viewing_")[1]
        try:
            prop_id = int(prop_id_str)
            p = await get_property_by_id(prop_id)
            title = p.get('title', f"Объект #{prop_id}") if p else f"Объект #{prop_id}"
            loc = p.get('city', 'Северный Кипр') if p else ""
            price = p.get('price', '') if p else ""
            curr = p.get('currency', 'GBP') if p else ""
            price_str = f"{price:,.0f} {curr}" if price else "По запросу"
        except Exception:
            title = f"Объект #{prop_id_str}"
            loc = ""
            price_str = "По запросу"

        # Уведомляем старшего риелтора
        try:
            username_str = f" (@{user.username})" if user.username else ""
            alert_text = (
                f"🏠 <b>Запрос на просмотр объекта!</b>\n\n"
                f"• <b>Клиент</b>: {user.full_name or 'Не указано'}{username_str}\n"
                f"• <b>ID клиента</b>: <code>{user.id}</code>\n"
                f"• <b>Объект</b>: <b>{title}</b> (ID: #{prop_id_str})\n"
                f"• <b>Локация</b>: {loc}\n"
                f"• <b>Цена</b>: {price_str}\n"
            )
            await notify_managers(context.bot, alert_text)
        except Exception as e:
            print(f"⚠️ Ошибка отправки заявки на просмотр: {e}")

        await safe_reply(
            query.message,
            f"✅ <b>Заявка на просмотр принята!</b>\n\n"
            f"Мы передали информацию по объекту «{html.escape(title)}» нашему старшему риелтору Илье (@makler_cy).\n"
            f"Он свяжется с вами в течение 10–15 минут для согласования удобного времени просмотра! 🤝\n\n"
            f"Также вы можете написать ему напрямую: <a href=\"https://t.me/makler_cy\">Илья @makler_cy</a>",
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    elif data == "contact_manager" or data.startswith("contact_manager_"):
        prop_id_str = data.split("contact_manager_")[1] if data.startswith("contact_manager_") else None

        # Получаем данные клиента из базы
        client_data = await get_or_create_client(user.id)
        deal_type = client_data.get("listing_type")
        if deal_type == "rent":
            deal_str = "🏖 Посуточная / сезонная аренда"
        elif deal_type == "sale":
            deal_str = "💰 Покупка недвижимости"
        else:
            deal_str = "Не указан (уточняется)"

        city = client_data.get("preferred_city") or "Не указан (любой)"
        district = client_data.get("preferred_district")
        city_full = f"{city} ({district})" if district else city

        prop_type = client_data.get("preferred_type") or "Любой (квартира / вилла)"

        b_min = client_data.get("bedrooms_min")
        b_max = client_data.get("bedrooms_max")
        if b_min is not None and b_max is not None:
            bedrooms_str = f"{b_min} сп." if b_min == b_max else f"{b_min} - {b_max} сп."
        elif b_min is not None:
            bedrooms_str = f"от {b_min} сп."
        else:
            bedrooms_str = "Не указано"

        start_d = client_data.get("booking_start_date")
        end_d = client_data.get("booking_end_date")
        if start_d and end_d:
            dates_str = f"с {start_d} по {end_d}"
        elif start_d:
            dates_str = f"с {start_d}"
        else:
            dates_str = "Не указаны (или долгосрок / покупка)"

        bg_min = client_data.get("budget_min")
        bg_max = client_data.get("budget_max")
        curr_symbol = "€/сутки" if deal_type == "rent" else "£"
        if bg_min and bg_max:
            budget_str = f"{bg_min:,.0f} - {bg_max:,.0f} {curr_symbol}"
        elif bg_max:
            budget_str = f"до {bg_max:,.0f} {curr_symbol}"
        elif bg_min:
            budget_str = f"от {bg_min:,.0f} {curr_symbol}"
        else:
            budget_str = "Не указан"

        prop_block = ""
        if prop_id_str and prop_id_str.isdigit():
            p = await get_property_by_id(int(prop_id_str))
            if p:
                p_title = p.get('title', f"Объект #{prop_id_str}")
                p_city = p.get('city', 'Северный Кипр')
                p_price = p.get('price', 0)
                p_curr = p.get('currency', 'GBP')
                p_price_str = f"£{p_price:,.0f}" if p_curr == 'GBP' else f"{p_price:,.0f} {p_curr}"
                prop_block = (
                    f"🏠 <b>Конкретный объект интереса:</b>\n"
                    f"• <b>Название:</b> {html.escape(p_title)}\n"
                    f"• <b>ID:</b> #{prop_id_str}\n"
                    f"• <b>Локация:</b> {html.escape(p_city)}\n"
                    f"• <b>Цена:</b> {p_price_str}\n\n"
                )

        selected_ids = get_user_search_results(user.id, client_data)
        offers_block = ""
        if selected_ids and not prop_block:
            offers_block = f"🔍 <b>Объекты в текущей подборке:</b> #{', #'.join(str(i) for i in selected_ids[:4])}\n\n"

        username_str = f" (@{user.username})" if user.username else ""
        phone_str = f"\n• <b>Телефон:</b> <code>{client_data.get('phone')}</code>" if client_data.get('phone') else ""

        manager_msg = (
            f"🛎 <b>ЗАПРОС СВЯЗИ С МЕНЕДЖЕРОМ!</b>\n\n"
            f"👤 <b>Клиент:</b> {html.escape(user.full_name or 'Не указано')}{username_str}\n"
            f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>{phone_str}\n"
            f"💬 <b>Открыть диалог:</b> <a href=\"tg://user?id={user.id}\">Написать клиенту</a>\n\n"
            f"{prop_block}"
            f"{offers_block}"
            f"📋 <b>Вся информация по квалификации:</b>\n"
            f"• <b>Тип сделки:</b> {deal_str}\n"
            f"• <b>Регион:</b> {city_full}\n"
            f"• <b>Тип жилья:</b> {prop_type}\n"
            f"• <b>Спальни:</b> {bedrooms_str}\n"
            f"• <b>Даты проживания:</b> {dates_str}\n"
            f"• <b>Бюджет:</b> {budget_str}\n"
        )

        try:
            await notify_managers(context.bot, manager_msg)
        except Exception as e:
            print(f"⚠️ Ошибка отправки уведомления менеджеру: {e}")

        await safe_reply(
            query.message,
            f"✅ <b>Ваш запрос передан старшему риелтору!</b>\n\n"
            f"Вся информация по вашим пожеланиям (локация, даты, спальни, бюджет) отправлена нашему эксперту <b>Илье (@makler_cy)</b>.\n\n"
            f"Он изучит детали и свяжется с вами в Telegram в ближайшее время! 🤝\n\n"
            f"Также вы можете перейти в чат с ним напрямую:",
            parse_mode="HTML",
            reply_markup=get_contact_manager_keyboard()
        )
