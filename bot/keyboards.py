# -*- coding: utf-8 -*-
"""
keyboards.py — Модуль клавиатур Telegram бота.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура бота."""
    keyboard = [
        [KeyboardButton("🏠 Подобрать недвижимость"), KeyboardButton("📊 Аналитика рынка")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_cities_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора города."""
    keyboard = [
        [
            InlineKeyboardButton("🏰 Кирения (Girne)", callback_data="city_Kyrenia"),
            InlineKeyboardButton("🌊 Искеле (Iskele)", callback_data="city_Iskele")
        ],
        [
            InlineKeyboardButton("🏛 Фамагуста", callback_data="city_Famagusta"),
            InlineKeyboardButton("🌆 Никосия (Lefkoşa)", callback_data="city_Nicosia")
        ],
        [
            InlineKeyboardButton("🍊 Гюзельюрт (Лефке, Газиверен)", callback_data="city_Guzelyurt")
        ],
        [
            InlineKeyboardButton("🌐 Все города", callback_data="city_all")
        ],
        [
            InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_property_types_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа недвижимости."""
    keyboard = [
        [
            InlineKeyboardButton("🏢 Квартира", callback_data="type_apartment"),
            InlineKeyboardButton("🏡 Вилла", callback_data="type_villa")
        ],
        [
            InlineKeyboardButton("🏙 Пентхаус", callback_data="type_penthouse"),
            InlineKeyboardButton("📦 Студия", callback_data="type_studio")
        ],
        [
            InlineKeyboardButton("🔙 Назад к выбору региона", callback_data="back_to_cities")
        ],
        [
            InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_deal_types_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора цели (покупка или аренда)."""
    keyboard = [
        [
            InlineKeyboardButton("💰 Покупка", callback_data="deal_sale"),
            InlineKeyboardButton("🏖 Аренда", callback_data="deal_rent")
        ],
        [
            InlineKeyboardButton("🔙 Назад к выбору региона", callback_data="back_to_cities")
        ],
        [
            InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_analytics_periods_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора временного периода макро-аналитики рынка."""
    keyboard = [
        [
            InlineKeyboardButton("📅 За последний месяц", callback_data="aperiod_1m"),
            InlineKeyboardButton("📈 Динамика за 2 месяца", callback_data="aperiod_2m")
        ],
        [
            InlineKeyboardButton("📊 Тренды за 3 месяца", callback_data="aperiod_3m"),
            InlineKeyboardButton("🌐 За всё время (май–сент)", callback_data="aperiod_all")
        ],
        [
            InlineKeyboardButton("⚖️ Налоги и ВНЖ 2026", callback_data="aperiod_legal")
        ],
        [
            InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_analytics_back_keyboard() -> InlineKeyboardMarkup:
    """Кнопка возврата к выбору периода аналитики."""
    keyboard = [
        [InlineKeyboardButton("🔙 К выбору периода аналитики", callback_data="aperiod_menu")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_property_card_keyboard(prop_id: int = None) -> InlineKeyboardMarkup:
    """Клавиатура карточки объекта с кнопкой связи с менеджером и возврата к подборке."""
    callback_data = f"contact_manager_{prop_id}" if prop_id else "contact_manager"
    keyboard = [
        [
            InlineKeyboardButton("💬 Написать менеджеру", callback_data=callback_data)
        ],
        [
            InlineKeyboardButton("🔙 Назад к выбору объектов", callback_data="back_to_search")
        ],
        [
            InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_search_results_keyboard(property_ids: list) -> InlineKeyboardMarkup:
    """Клавиатура для сообщения со списком найденных объектов."""
    keyboard = []
    if property_ids:
        # Группируем кнопки по 2 в ряд для удобного отображения без обрезки текста
        row = []
        for idx, pid in enumerate(property_ids[:4], 1):
            num_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"][idx - 1]
            row.append(InlineKeyboardButton(f"{num_emoji} Подробнее", callback_data=f"prop_card_{pid}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([
            InlineKeyboardButton("💬 Связаться с менеджером", callback_data="contact_manager")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 Новый поиск", callback_data="restart_search")
        ])
        keyboard.append([
            InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("🔙 Назад к поиску объектов", callback_data="restart_search")
        ])
        keyboard.append([
            InlineKeyboardButton("💬 Связаться с менеджером", callback_data="contact_manager")
        ])
        keyboard.append([
            InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")
        ])
    return InlineKeyboardMarkup(keyboard)


def get_contact_manager_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после отправки запроса менеджеру."""
    keyboard = [
        [
            InlineKeyboardButton("💬 Перейти в чат с Ильей (@makler_cy)", url="https://t.me/makler_cy")
        ],
        [
            InlineKeyboardButton("🔙 Назад к выбору объектов", callback_data="back_to_search")
        ],
        [
            InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)



