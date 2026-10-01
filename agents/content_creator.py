# -*- coding: utf-8 -*-
"""
content_creator.py — Агент-контентмейкер: генерирует описания объектов,
посты для соцсетей, email-рассылки.
"""

import os
import json
from tools.llm import ask_llm

CONTENT_PROMPT = """Ты — профессиональный копирайтер для агентства недвижимости на Северном Кипре.
Пишешь на русском языке продающие тексты для Telegram/Instagram.

Твоя задача — строго придерживаться Tone of Voice (стиля общения) нашего агентства на основе успешных примеров ниже.

Примеры лучших постов агентства (используй их структуру, стиль эмодзи, абзацы и Tone of Voice):
{examples}

Правила:
- Пиши эмоционально, но достоверно, вовлекая читателя.
- Обязательно выделяй фишки и преимущества (вид на море, бассейн, беспроцентная рассрочка, близко к морю/университету).
- Разделяй текст на абзацы, используй списки с эмодзи для легкой читаемости.
- Добавляй призыв к действию в конце (например, приглашение написать в чат).
- Заканчивай пост 5-7 релевантными хештегами.
"""


def _load_examples() -> str:
    """Загружает примеры постов."""
    examples_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'content_examples.json')
    try:
        with open(examples_path, 'r', encoding='utf-8') as f:
            examples = json.load(f)
            formatted = ""
            for ex in examples:
                formatted += f"--- ТИП: {ex['type']} ({ex['title']}) ---\n{ex['text']}\n\n"
            return formatted
    except Exception as e:
        print(f"⚠️ Ошибка загрузки примеров контента: {e}")
        return "Примеры постов недоступны."


async def create_listing_description(property_data: dict) -> str:
    """Создаёт описание объекта для объявления."""
    info = _property_to_text(property_data)
    examples = _load_examples()

    response = await ask_llm(
        system_prompt=CONTENT_PROMPT.format(examples=examples),
        user_message=f"""Напиши продающее описание для этого объекта недвижимости:
        
{info}

Напиши полноценный пост для Telegram-канала в стиле наших примеров, с цепляющим заголовком, фишками, условиями рассрочки/цены и призывом к действию.""",
        temperature=0.85,
        max_tokens=1000,
    )

    return response


async def create_social_post(property_data: dict, platform: str = "telegram") -> str:
    """Создаёт пост для соцсетей."""
    info = _property_to_text(property_data)
    examples = _load_examples()

    response = await ask_llm(
        system_prompt=CONTENT_PROMPT.format(examples=examples),
        user_message=f"""Напиши продающий пост для {platform} об этом объекте:

{info}

Пост должен быть кратким (до 600 символов), но невероятно вовлекающим, строго в фирменном стиле Tone of Voice.""",
        temperature=0.85,
        max_tokens=600,
    )

    return response


def _property_to_text(data: dict) -> str:
    """Конвертирует данные объекта в текст."""
    parts = []
    if data.get('title'):
        parts.append(f"Название: {data['title']}")
    if data.get('property_type'):
        parts.append(f"Тип: {data['property_type']}")
    if data.get('city'):
        parts.append(f"Город: {data['city']}")
    if data.get('district'):
        parts.append(f"Район: {data['district']}")
    if data.get('price'):
        parts.append(f"Цена: {data['price']} {data.get('currency', 'GBP')}")
    if data.get('bedrooms'):
        parts.append(f"Спален: {data['bedrooms']}")
    if data.get('area_m2'):
        parts.append(f"Площадь: {data['area_m2']} м²")
    if data.get('description'):
        parts.append(f"Описание: {data['description'][:300]}")
    return "\n".join(parts)
