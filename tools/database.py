# -*- coding: utf-8 -*-
"""
database.py — Модуль работы с базой данных объектов недвижимости.
SQLite для хранения объектов, клиентов и их связей.
"""

import aiosqlite
import sqlite3
import os
import sys
import json
from datetime import datetime

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'properties.db')


def get_sync_db(timeout: float = 10.0) -> sqlite3.Connection:
    """Возвращает синхронное подключение к SQLite с защитой от блокировок."""
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.execute("PRAGMA busy_timeout = 10000;")
    return conn


async def init_db():
    """Создаёт таблицы если их нет, включает WAL-режим и таймаут занятости базы."""
    async with aiosqlite.connect(DB_PATH, timeout=10.0) as db:
        await db.execute('PRAGMA journal_mode = WAL;')
        await db.execute('PRAGMA busy_timeout = 10000;')
        await db.execute('PRAGMA synchronous = NORMAL;')
        # Таблица объектов недвижимости
        await db.execute('''
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT DEFAULT 'manual',
                source_url TEXT,
                title TEXT NOT NULL,
                property_type TEXT,
                listing_type TEXT DEFAULT 'sale',
                city TEXT,
                district TEXT,
                price REAL,
                currency TEXT DEFAULT 'GBP',
                bedrooms INTEGER,
                bathrooms INTEGER,
                area_m2 REAL,
                floor INTEGER,
                total_floors INTEGER,
                year_built INTEGER,
                description TEXT,
                features TEXT,
                photos TEXT,
                contact_name TEXT,
                contact_phone TEXT,
                latitude REAL,
                longitude REAL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                price_per_day REAL,
                channel_tag TEXT
            )
        ''')
        # Автоматическая миграция для существующих баз данных
        try:
            await db.execute('ALTER TABLE properties ADD COLUMN price_per_day REAL;')
        except Exception:
            pass
        try:
            await db.execute('ALTER TABLE properties ADD COLUMN channel_tag TEXT;')
        except Exception:
            pass

        # Таблица клиентов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                name TEXT,
                phone TEXT,
                budget_min REAL,
                budget_max REAL,
                preferred_city TEXT,
                preferred_district TEXT,
                preferred_type TEXT,
                bedrooms_min INTEGER,
                bedrooms_max INTEGER,
                listing_type TEXT,
                booking_start_date TEXT,
                booking_end_date TEXT,
                notes TEXT,
                status TEXT DEFAULT 'new',
                priority TEXT DEFAULT 'warm',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица бронирований (календарь занятости)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER,
                start_date TEXT, -- YYYY-MM-DD
                end_date TEXT,   -- YYYY-MM-DD
                status TEXT DEFAULT 'confirmed',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties(id)
            )
        ''')

        # Таблица взаимодействий
        await db.execute('''
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                agent_name TEXT,
                action TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        ''')

        # Проверяем колонку price_per_day
        cursor = await db.execute("PRAGMA table_info(properties)")
        cols = [r[1] for r in await cursor.fetchall()]
        if 'price_per_day' not in cols:
            await db.execute("ALTER TABLE properties ADD COLUMN price_per_day REAL")

        await db.commit()
    print("✅ База данных инициализирована")


async def add_property(data: dict) -> int:
    """Добавляет объект в базу. Возвращает ID."""
    async with aiosqlite.connect(DB_PATH, timeout=10.0) as db:
        cursor = await db.execute('''
            INSERT INTO properties (
                source, source_url, title, property_type, listing_type,
                city, district, price, currency, bedrooms, bathrooms,
                area_m2, floor, total_floors, year_built, description,
                features, photos, contact_name, contact_phone,
                latitude, longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('source', 'manual'),
            data.get('source_url'),
            data.get('title', 'Без названия'),
            data.get('property_type'),
            data.get('listing_type', 'sale'),
            data.get('city'),
            data.get('district'),
            data.get('price'),
            data.get('currency', 'GBP'),
            data.get('bedrooms'),
            data.get('bathrooms'),
            data.get('area_m2'),
            data.get('floor'),
            data.get('total_floors'),
            data.get('year_built'),
            data.get('description'),
            json.dumps(data.get('features', []), ensure_ascii=False),
            json.dumps(data.get('photos', []), ensure_ascii=False),
            data.get('contact_name'),
            data.get('contact_phone'),
            data.get('latitude'),
            data.get('longitude'),
        ))
        await db.commit()
        return cursor.lastrowid


def normalize_city(city: str) -> str:
    """Нормализует название города."""
    if not city:
        return None
    c = city.lower().strip()
    mapping = {
        'kyrenia': 'Кирения', 'girne': 'Кирения', 'кирения': 'Кирения', 'гирне': 'Кирения', 'alsancak': 'Кирения', 'алсанджак': 'Кирения',
        'iskele': 'Искеле', 'трикомо': 'Искеле', 'искеле': 'Искеле', 'long beach': 'Искеле',
        'famagusta': 'Фамагуста', 'gazimagusa': 'Фамагуста', 'фамагуста': 'Фамагуста', 'газимагуса': 'Фамагуста',
        'nicosia': 'Никосия', 'lefkosa': 'Никосия', 'никосия': 'Никосия', 'лефкоша': 'Никосия',
        'guzelyurt': 'Гюзельюрт', 'гюзельюрт': 'Гюзельюрт', 'морфу': 'Гюзельюрт',
        'lefke': 'Гюзельюрт', 'лефке': 'Гюзельюрт', 'gaziveren': 'Гюзельюрт', 'газиверен': 'Гюзельюрт'
    }
    for key, val in mapping.items():
        if key in c or c in key:
            return val
    return city


def normalize_type(prop_type: str) -> str:
    """Нормализует тип недвижимости (поддерживает мультивыбор, например вилла или пентхаус)."""
    if not prop_type:
        return None
    t = prop_type.lower().strip()
    if any(k in t for k in ['недвижим', 'любой', 'все', 'all', 'any', 'property', 'real estate']):
        return None
    types = []
    if 'villa' in t or 'вилл' in t or 'дом' in t or 'house' in t:
        types.append('вилла')
    if 'penthouse' in t or 'пентхаус' in t:
        types.append('пентхаус')
    if 'studio' in t or 'студи' in t:
        types.append('студия')
    if 'land' in t or 'участок' in t or 'земл' in t:
        types.append('участок')
    if 'apart' in t or 'flat' in t or 'квартир' in t or 'апартамент' in t:
        types.append('квартира')
    if len(types) > 1:
        return ",".join(types)
    elif len(types) == 1:
        return types[0]
    return None if any(k in t for k in ['недвижим', 'любой', 'все']) else prop_type


async def search_properties(
    city: str = None,
    property_type: str = None,
    listing_type: str = None,
    price_min: float = None,
    price_max: float = None,
    bedrooms_min: int = None,
    bedrooms_max: int = None,
    bedrooms_list: list = None,
    limit: int = 10,
    rent_term: str = None,  # 'short', 'long', or None
    booking_start: str = None, # YYYY-MM-DD
    booking_end: str = None    # YYYY-MM-DD
) -> list:
    """Ищет объекты по критериям с гибким фоллбэком и фильтрацией по календарю бронирований."""
    norm_city = normalize_city(city)
    norm_type = normalize_type(property_type)

    async def _execute_search(c_filter, t_filter, l_filter, b_min, b_max):
        query = "SELECT * FROM properties WHERE is_active = 1"
        params = []
        if c_filter:
            if any(k in c_filter.lower() for k in ['гюзел', 'лефк', 'газив', 'морфу', 'guzel', 'lefk', 'gaziv']):
                query += " AND (LOWER(city) LIKE '%гюзел%' OR LOWER(city) LIKE '%guzel%' OR LOWER(city) LIKE '%лефк%' OR LOWER(city) LIKE '%lefk%' OR LOWER(district) LIKE '%газив%' OR LOWER(district) LIKE '%gaziv%' OR LOWER(district) LIKE '%лефк%' OR LOWER(district) LIKE '%гюзел%' OR LOWER(description) LIKE '%газиверен%' OR LOWER(description) LIKE '%лефке%' OR LOWER(description) LIKE '%гюзельюрт%')"
            else:
                query += " AND (LOWER(city) LIKE ? OR LOWER(district) LIKE ?)"
                params.extend([f"%{c_filter.lower()}%", f"%{c_filter.lower()}%"])
        if t_filter:
            if ',' in t_filter:
                sub_clauses = ["LOWER(property_type) LIKE ?" for _ in t_filter.split(',')]
                query += f" AND ({' OR '.join(sub_clauses)})"
                for tf in t_filter.split(','):
                    params.append(f"%{tf.strip().lower()}%")
            else:
                query += " AND LOWER(property_type) LIKE ?"
                params.append(f"%{t_filter.lower()}%")
        if l_filter and l_filter != 'all':
            query += " AND listing_type = ?"
            params.append(l_filter)
            
            # Фильтрация по календарю бронирований (исключаем пересекающиеся брони)
            if l_filter == 'rent' and booking_start and booking_end:
                query += " AND id NOT IN (SELECT property_id FROM bookings WHERE start_date <= ? AND end_date >= ?)"
                params.extend([booking_end, booking_start])
            
            # Фильтрация по сроку аренды (СТРОГО ДЛЯ АРЕНДЫ!)
            if l_filter == 'rent':
                is_short = (rent_term == 'short' or (booking_start and booking_end))
                if is_short:
                    query += " AND (price_per_day IS NOT NULL OR LOWER(description) LIKE '%сутки%' OR LOWER(description) LIKE '%посуточн%' OR LOWER(description) LIKE '%daily%')"
                    query += " AND LOWER(description) NOT LIKE '%сдали%' AND LOWER(description) NOT LIKE '%сдано%'"
                elif rent_term == 'long':
                    query += " AND (LOWER(description) LIKE '%длительн%' OR LOWER(description) LIKE '%год%' OR LOWER(description) LIKE '%long term%')"

        price_col = "COALESCE(price_per_day, price)" if (l_filter == 'rent' and (rent_term == 'short' or (booking_start and booking_end))) else "price"

        try:
            if b_min is not None and float(b_min) > 0:
                query += f" AND {price_col} >= ?"
                params.append(float(b_min))
        except (ValueError, TypeError):
            pass

        try:
            if b_max is not None and float(b_max) > 0:
                query += f" AND {price_col} <= ?"
                params.append(float(b_max))
        except (ValueError, TypeError):
            pass

        try:
            if bedrooms_list:
                b_set = set(bedrooms_list)
                has_studio = 0 in b_set
                non_zero = [b for b in bedrooms_list if b > 0]
                if has_studio and non_zero:
                    ph = ', '.join(['?'] * len(non_zero))
                    query += f" AND (bedrooms IN ({ph}) OR bedrooms = 0 OR LOWER(property_type) LIKE '%студи%' OR LOWER(title) LIKE '%студи%')"
                    params.extend(non_zero)
                elif has_studio:
                    query += " AND (bedrooms = 0 OR LOWER(property_type) LIKE '%студи%' OR LOWER(title) LIKE '%студи%')"
                elif non_zero:
                    ph = ', '.join(['?'] * len(non_zero))
                    query += f" AND bedrooms IN ({ph}) AND LOWER(property_type) NOT LIKE '%студи%' AND LOWER(title) NOT LIKE '%студи%'"
                    params.extend(non_zero)
            elif bedrooms_min is not None:
                b_val = int(bedrooms_min)
                if bedrooms_max is not None:
                    b_max_val = int(bedrooms_max)
                    if b_val == b_max_val:
                        if b_val == 0 or (norm_type and 'студи' in norm_type):
                            query += " AND (bedrooms = 0 OR LOWER(property_type) LIKE '%студи%' OR LOWER(title) LIKE '%студи%')"
                        else:
                            query += " AND bedrooms = ? AND LOWER(property_type) NOT LIKE '%студи%' AND LOWER(title) NOT LIKE '%студи%'"
                            params.append(b_val)
                    else:
                        if b_val == 0:
                            query += " AND (bedrooms BETWEEN 0 AND ? OR LOWER(property_type) LIKE '%студи%' OR LOWER(title) LIKE '%студи%')"
                            params.append(b_max_val)
                        else:
                            query += " AND bedrooms BETWEEN ? AND ? AND LOWER(property_type) NOT LIKE '%студи%' AND LOWER(title) NOT LIKE '%студи%'"
                            params.extend([b_val, b_max_val])
                elif b_val == 0 or (norm_type and 'студи' in norm_type):
                    query += " AND (bedrooms = 0 OR LOWER(property_type) LIKE '%студи%' OR LOWER(title) LIKE '%студи%')"
                else:
                    query += " AND bedrooms = ? AND LOWER(property_type) NOT LIKE '%студи%' AND LOWER(title) NOT LIKE '%студи%'"
                    params.append(b_val)
        except (ValueError, TypeError):
            pass

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(DB_PATH, timeout=10.0) as db:
            await db.create_function("lower", 1, lambda x: str(x).lower() if x is not None else "")
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            seen_titles = set()
            unique_results = []
            for row in rows:
                p = dict(row)
                title = p.get('title', '').strip().lower()
                if title not in seen_titles:
                    seen_titles.add(title)
                    unique_results.append(p)
            return unique_results

    # 1. Попытка точного поиска (город + тип + сделка + спальни + цена)
    res = await _execute_search(norm_city, norm_type, listing_type, price_min, price_max)
    if res:
        return res

    # 2. Поиск по городу + типу + сделке + точным спальням без ограничения цены (показываем чуть выше бюджета)
    res = await _execute_search(norm_city, norm_type, listing_type, None, None)
    if res:
        return res

    # 3. Поиск по городу + сделке + точным спальням (если тип не совпал)
    if norm_type:
        res = await _execute_search(norm_city, None, listing_type, price_min, price_max)
        if res:
            return res
        res = await _execute_search(norm_city, None, listing_type, None, None)
        if res:
            return res

    # 4. Если задан город, но ничего не найдено - пробуем без фильтра по городу (альтернативный регион)
    if norm_city:
        res = await _execute_search(None, norm_type, listing_type, price_min, price_max)
        if res:
            return res
        res = await _execute_search(None, None, listing_type, price_min, price_max)
        if res:
            return res

    return []


async def get_or_create_client(telegram_id: int, name: str = None) -> dict:
    """Находит или создаёт клиента по Telegram ID."""
    async with aiosqlite.connect(DB_PATH, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()

        if row:
            return dict(row)

        # Создаём нового
        cursor = await db.execute(
            "INSERT INTO clients (telegram_id, name) VALUES (?, ?)",
            (telegram_id, name or "Неизвестный")
        )
        await db.commit()
        new_id = cursor.lastrowid

        cursor = await db.execute("SELECT * FROM clients WHERE id = ?", (new_id,))
        row = await cursor.fetchone()
        return dict(row)


async def update_client(telegram_id: int, **kwargs):
    """Обновляет данные клиента."""
    if not kwargs:
        return

    fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [telegram_id]

    async with aiosqlite.connect(DB_PATH, timeout=10.0) as db:
        await db.execute(
            f"UPDATE clients SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
            values
        )
        await db.commit()


async def log_interaction(client_id: int, agent_name: str, action: str, details: str = None):
    """Логирует взаимодействие агента с клиентом."""
    async with aiosqlite.connect(DB_PATH, timeout=10.0) as db:
        await db.execute(
            "INSERT INTO interactions (client_id, agent_name, action, details) VALUES (?, ?, ?, ?)",
            (client_id, agent_name, action, details)
        )
        await db.commit()


async def get_property_stats() -> dict:
    """Возвращает статистику по объектам."""
    async with aiosqlite.connect(DB_PATH, timeout=10.0) as db:
        stats = {}

        cursor = await db.execute("SELECT COUNT(*) FROM properties WHERE is_active = 1")
        stats['total'] = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT city, COUNT(*) as cnt, AVG(price) as avg_price "
            "FROM properties WHERE is_active = 1 AND price > 0 "
            "GROUP BY city ORDER BY cnt DESC"
        )
        stats['by_city'] = [
            {'city': row[0], 'count': row[1], 'avg_price': round(row[2], 0)}
            for row in await cursor.fetchall()
        ]

        return stats


async def get_property_by_id(property_id: int) -> dict:
    """Возвращает объект недвижимости по его ID."""
    async with aiosqlite.connect(DB_PATH, timeout=10.0) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM properties WHERE id = ?", (property_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
