# -*- coding: utf-8 -*-
"""
property_matcher.py — Агент-подборщик: ищет объекты по критериям клиента,
форматирует красивую подборку.
"""

import json
import re
from datetime import datetime
from tools.llm import ask_llm
from tools.database import search_properties

MATCHER_PROMPT = """Ты — опытный риелтор-аналитик недвижимости Северного Кипра.
Тебе дан список кандидатов из базы данных и оригинальный запрос клиента.

Твоя задача:
1. Выбери из списка кандидатов СТРОГО только те объекты, которые соответствуют или максимально близки к запросу (по городу, бюджету, спальням, типу сделки). Исключи из списка все объекты, которые категорически не подходят. Оставь максимум 3-4 наиболее подходящих объекта.
2. Для каждого выбранного объекта напиши короткий комментарий (1-2 предложения) на русском языке: почему этот объект рекомендуется.
3. Выдели лучший объект из списка в качестве рекомендации эксперта.

⚠️ **КРИТИЧЕСКИЕ ПРАВИЛА БЕЗОПАСНОСТИ И ДОСТОВЕРНОСТИ (НИКАКИХ ГАЛЛЮЦИНАЦИЙ):**
*   **СТРОГО ЗАПРЕЩЕНО ВЫДУМЫВАТЬ ТИП И ЛОКАЦИЮ ОБЪЕКТА!**
    - Если объект — апартаменты/квартира в комплексе Panorama Long Beach (Искеле), КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО называть его «виллой», «коттеджем» или приписывать ему другой район (например, Боаз)! Пиши строго о том объекте и локации, которые указаны в карточке кандидата.
    - Никогда не додумывай несуществующие детали: «для развлечений», «шумных вечеринок» и т.п. Пиши только о реальных преимуществах: близость к пляжу Лонг Бич, инфраструктура комплекса, просторная планировка для семьи/компании.
*   **Запрещено менять реальную локацию объекта!** Если в данных кандидата написано «Город: Искеле», пиши строго про Искеле / Long Beach.
*   **Никаких цифр и цен в тексте комментария!** Не упоминай в тексте комментария стоимость, количество спален или площадь (например, не пиши: "за 140 евро", "с двумя спальнями"). Все эти параметры выводятся в карточке автоматически.
*   **Соответствие сделке:** Если клиент ищет АРЕНДУ — категорически запрещено писать про "рассрочку", "инвестиции" или "покупку"!

Ответ выведи СТРОГО в формате JSON без какого-либо другого текста, разметки или markdown-блоков (без ```json):
{
  "selected_indices": [
    {
      "index": 1,
      "comment": "Отличная локация рядом с морем, развитая инфраструктура комплекса и бассейн."
    }
  ],
  "expert_recommendation": "Рекомендуем рассмотреть объект №1..."
}
"""


def extract_property_daily_price(p: dict) -> float | None:
    """Извлекает реальную суточную цену объекта, исключая коммунальные услуги и долгосрочные тарифы."""
    ppd = p.get('price_per_day')
    if ppd and float(ppd) >= 20:
        return float(ppd)

    desc = p.get('description') or ''
    for line in desc.split('\n'):
        line_clean = line.strip()
        if not line_clean or re.search(r'(?:коммунал|уборк|депозит|счетчик|счётчик|резервац|залог)', line_clean, re.I):
            continue
        m = re.search(r'(\d+)\s*(?:€|EUR|GBP|£)\s*(?:/?\s*(?:сутки|суток|сут|ночь|ночи|ночей|день|дня|дней)|в сутки|в день)?', line_clean, re.I)
        if m and re.search(r'(?:сутки|суток|сут|ночь|ночи|ночей|день|дня|дней|посуточн)', line_clean, re.I):
            val = float(m.group(1))
            if 20 <= val <= 1000:
                return val
        m2 = re.search(r'(?:посуточн\w*|цена|стоимость)[^\d\n]*(?:от\s*\d+\s*(?:ноч\w*|дн\w*))?[^\d\n]*(\d+)\s*(?:€|EUR|GBP|£)', line_clean, re.I)
        if m2:
            val = float(m2.group(1))
            if 20 <= val <= 1000:
                return val
        m3 = re.search(r'(\d+)\s*(?:€|EUR|GBP|£)?\s*(?:/|в)?\s*(?:сутки|ночь|день)', line_clean, re.I)
        if m3:
            val = float(m3.group(1))
            if 20 <= val <= 1000:
                return val

    price = p.get('price')
    if price and 20 <= float(price) <= 300:
        return float(price)
    return None


def format_property_price(p: dict, params: dict = None) -> str:
    """Форматирует цену объекта с учетом посуточной или долгосрочной аренды."""
    params = params or {}
    listing_type = p.get('listing_type') or params.get('listing_type', 'sale')
    desc = p.get('description') or ''
    curr = p.get('currency', 'EUR')
    curr_sym = '€' if curr == 'EUR' else ('£' if curr == 'GBP' else '$')
    raw_price = p.get('price', 0)
    
    start_date = params.get('booking_start_date')
    end_date = params.get('booking_end_date')
    days = 0
    if start_date and end_date:
        try:
            d1 = datetime.strptime(start_date, "%Y-%m-%d")
            d2 = datetime.strptime(end_date, "%Y-%m-%d")
            days = (d2 - d1).days
        except Exception:
            days = 0
            
    daily_val = extract_property_daily_price(p)
    is_short = bool(days > 0 or params.get('rent_term') == 'short' or daily_val is not None or 'сутки' in desc.lower() or 'посуточн' in desc.lower())
    
    m_monthly = re.search(r'(\d+[\s\d]*)\s*(?:€|EUR|GBP|£)?\s*(?:в месяц|/месяц|/ месяц|евро в месяц)', desc, re.I)
    monthly_val = int(m_monthly.group(1).replace(' ', '')) if m_monthly else None
    
    if listing_type == 'rent':
        if is_short and (daily_val or (raw_price and raw_price <= 400 and not monthly_val)):
            d_price = int(daily_val) if daily_val else int(raw_price)
            if days > 0:
                total = d_price * days
                return f"{d_price} {curr_sym}/сутки (~{total} {curr_sym} за {days} ноч.)"
            else:
                return f"{d_price} {curr_sym}/сутки"
        elif monthly_val:
            return f"{monthly_val} {curr_sym}/месяц"
        else:
            return f"{raw_price:,.0f} {curr_sym}/месяц"
    else:
        return f"{curr_sym}{raw_price:,.0f}" if curr_sym == '£' else f"{raw_price:,.0f} {curr_sym}"


async def find_properties(params: dict, query: str = None) -> str:
    """
    Ищет объекты по критериям и форматирует подборку с использованием LLM.

    Args:
        params: dict с ключами city, property_type, listing_type,
                budget_min, budget_max, bedrooms
        query: Специфический текстовый запрос от пользователя (например, "с рассрочкой")

    Returns:
        Красиво отформатированный текст подборки.
    """
    # Определяем срок аренды по наличию дат или по ключевым словам
    rent_term = params.get('rent_term')
    if params.get('booking_start_date') and params.get('booking_end_date'):
        rent_term = 'short'
    elif query:
        q_low = query.lower()
        short_term_keywords = ["посуточно", "сутки", "несколько дней", "день", "дни", "short term", "daily", "пожить неделю", "две недели", "отпуск", "остановиться"]
        long_term_keywords = ["длительный", "длительно", "долгосрок", "на год", "год", "long term", "контракт"]
        if any(k in q_low for k in short_term_keywords):
            rent_term = 'short'
        elif any(k in q_low for k in long_term_keywords):
            rent_term = 'long'
    params['rent_term'] = rent_term

    # Загружаем до 10 объектов для ранжирования
    results = await search_properties(
        city=params.get('city'),
        property_type=params.get('property_type'),
        listing_type=params.get('listing_type'),
        price_min=params.get('budget_min'),
        price_max=params.get('budget_max'),
        bedrooms_min=params.get('bedrooms_min') if params.get('bedrooms_min') is not None else params.get('bedrooms'),
        bedrooms_max=params.get('bedrooms_max'),
        bedrooms_list=params.get('bedrooms_list'),
        limit=10,
        rent_term=rent_term,
        booking_start=params.get('booking_start_date'),
        booking_end=params.get('booking_end_date')
    )

    if not results:
        return (
            "😔 По указанным параметрам подходящих вариантов не найдено.\n\n"
            "Попробуйте изменить бюджет или выбрать другой город."
        ), []

    # Проверяем наличие предупреждений о несовпадении (регион или бюджет)
    req_city = params.get('city')
    req_budget = params.get('budget_max')
    req_beds_min = params.get('bedrooms_min') if params.get('bedrooms_min') is not None else params.get('bedrooms')
    req_beds_list = params.get('bedrooms_list')
    req_beds = req_beds_min
    has_warning = False
    has_city_diff = False
    has_price_diff = False
    has_bed_diff = False

    for p in results[:3]:
        p_c = (p.get('city') or '').lower().strip()
        p_d = (p.get('district') or '').lower().strip()
        is_same_city = req_city and req_city.lower().strip() == p_c
        if req_city and any(k in req_city.lower() for k in ['гюзел', 'лефк', 'газив', 'морфу', 'guzel', 'lefk', 'gaziv']):
            if any(k in p_c or k in p_d for k in ['гюзел', 'guzel', 'лефк', 'lefk', 'газив', 'gaziv']):
                is_same_city = True
        if req_city and p.get('city') and not is_same_city:
            has_warning = True
            has_city_diff = True
        d_p = extract_property_daily_price(p)
        is_daily = bool(rent_term == 'short' or (req_budget and float(req_budget) < 500) or d_p is not None)
        check_p = d_p if (is_daily and d_p) else p.get('price')
        if req_budget and check_p and float(check_p) > float(req_budget):
            has_warning = True
            has_price_diff = True
        if req_beds_list:
            if p.get('bedrooms') not in req_beds_list and (p.get('bedrooms') is not None and req_beds_min is not None and int(p.get('bedrooms')) < int(req_beds_min)):
                has_warning = True
                has_bed_diff = True
        elif req_beds and p.get('bedrooms') and int(p.get('bedrooms')) < int(req_beds):
            has_warning = True
            has_bed_diff = True

    if has_warning:
        if has_bed_diff and req_budget:
            bed_prices = [
                extract_property_daily_price(p)
                for p in results
                if p.get('bedrooms') and int(p.get('bedrooms')) >= int(req_beds) and extract_property_daily_price(p)
            ]
            min_bed_p = int(min(bed_prices)) if bed_prices else 65
            lines = [
                "🏠 **Подборка объектов**\n"
                f"💡 *В {req_city or 'этом регионе'} апартаменты с {req_beds} спальнями начинаются от {min_bed_p} €/сутки. "
                f"Подобрали отличные варианты 1+1 в вашем бюджете (до {int(req_budget)} €/сутки), а также ближайший вариант с {req_beds} спальнями:*\n"
            ]
        elif has_price_diff:
            lines = [
                "🏠 **Подборка объектов**\n"
                f"⚠️ *В бюджете до {int(req_budget)} €/сутки в {req_city or 'этом районе'} свободных мест нет. Показываем наиболее близкие по цене варианты:*\n"
            ]
        elif has_city_diff:
            lines = [
                "🏠 **Подборка объектов**\n"
                f"⚠️ *В выбранном районе сейчас нет свободных мест на эти даты. Показываем наиболее близкие альтернативы в соседних регионах:*\n"
            ]
        else:
            lines = [
                "🏠 **Подборка объектов**\n"
                "⚠️ *Точных совпадений по всем критериям не найдено. Показываем наиболее близкие альтернативы:*\n"
            ]
    else:
        city_str = req_city or "Северному Кипру"
        lines = [f"🏠 **Подборка объектов по вашему запросу** ({city_str})\n"]

    selected_ids = []
    max_cards = 4
    for num, p in enumerate(results[:max_cards], 1):
        selected_ids.append(p['id'])
        title = p.get('title', 'Объект недвижимости')
        city = p.get('city', 'Северный Кипр')
        district = p.get('district', '')
        loc = f"{district}, {city}" if (district and district.lower().strip() != city.lower().strip()) else (district or city or "Северный Кипр")
        price_str = format_property_price(p, params)
        
        b_count = p.get('bedrooms')
        if b_count == 0 or (p.get('property_type') and 'студи' in p.get('property_type').lower()):
            bed_str = "Студия"
        elif b_count == 1:
            bed_str = "1 спальня"
        elif b_count in [2, 3, 4]:
            bed_str = f"{b_count} спальни"
        elif b_count:
            bed_str = f"{b_count} спален"
        else:
            bed_str = "1 спальня"

        area = p.get('area_m2')
        area_str = f"{area:,.0f} м²" if area else "Не указана"

        raw_desc = (p.get('description') or '').strip()
        desc_lines = []
        for line in raw_desc.split('\n'):
            l_str = line.strip()
            if l_str and not re.search(r'#id\d+|t\.me|http|@\w+|подробнее|связаться', l_str, re.I):
                if l_str.lower() != title.lower() and l_str.lower() not in title.lower():
                    desc_lines.append(l_str)
                    if len(desc_lines) >= 2:
                        break
        first_line = ", ".join(desc_lines) if desc_lines else (raw_desc.split('\n')[0].strip() if raw_desc else "")
        if len(first_line) > 120:
            first_line = first_line[:120] + "..."

        features_str = ""
        if p.get('features'):
            try:
                fts = json.loads(p['features']) if isinstance(p['features'], str) else p['features']
                if fts:
                    features_str = f"ℹ️ _{', '.join(fts[:3])}_\n"
            except Exception:
                pass

        badge = ""
        d_p = extract_property_daily_price(p)
        is_daily = bool(params.get('rent_term') == 'short' or (req_budget and float(req_budget) < 500) or d_p is not None)
        check_p = d_p if (is_daily and d_p) else p.get('price')
        p_c = (p.get('city') or '').lower().strip()
        p_d = (p.get('district') or '').lower().strip()
        is_same_c = req_city and req_city.lower().strip() == p_c
        if req_city and any(k in req_city.lower() for k in ['гюзел', 'лефк', 'газив', 'морфу', 'guzel', 'lefk', 'gaziv']):
            if any(k in p_c or k in p_d for k in ['гюзел', 'guzel', 'лефк', 'lefk', 'газив', 'gaziv']):
                is_same_c = True
        if req_city and p.get('city') and not is_same_c:
            badge = f"📍 *Альтернативный регион ({city} вместо {req_city})*\n"
        elif req_beds_list and p.get('bedrooms') not in req_beds_list and req_beds_min is not None and p.get('bedrooms') is not None and int(p.get('bedrooms')) < int(req_beds_min):
            type_label = "Студия" if p.get('bedrooms') == 0 else "Вариант 1+1"
            badge = f"💡 *{type_label} в пределах вашего бюджета*\n"
        elif not req_beds_list and req_beds and p.get('bedrooms') is not None and int(p.get('bedrooms')) < int(req_beds):
            type_label = "Студия" if p.get('bedrooms') == 0 else "Вариант 1+1"
            badge = f"💡 *{type_label} в пределах вашего бюджета*\n"
        elif req_budget and check_p and float(check_p) > float(req_budget):
            badge = f"💎 *Вариант с {bed_str} (выше бюджета)*\n"

        card = (
            f"{num}️⃣ **{title}**\n"
            f"{badge}"
            f"📍 Локация: {loc}\n"
            f"💰 {price_str} | 🛏 {bed_str} | 📐 {area_str}\n"
            f"{features_str}"
            f"📝 _{first_line}_\n"
        )
        lines.append(card)

    if len(results) > max_cards:
        lines.append(f"💡 _Показано {max_cards} лучших варианта из {len(results)} доступных в базе. Для подробностей напишите номер варианта в чат!_")
    else:
        lines.append("💡 _Для подробностей просто напишите номер варианта в чат!_")

    if len(selected_ids) > 1:
        lines.append("---\n⭐ **Рекомендация эксперта:** Рекомендуем рассмотреть вариант №1 — он отлично подходит по соотношению цены и локации.")

    return "\n".join(lines), selected_ids


def _format_properties_for_llm(properties: list, params: dict = None) -> str:
    """Форматирует объекты в текст для LLM."""
    lines = []
    for i, p in enumerate(properties, 1):
        p_type = p.get('property_type') or 'апартаменты / квартира'
        if p_type in ['', None, '']:
            p_type = 'апартаменты / квартира'
        city = p.get('city') or 'Искеле'
        if city in ['', None, '']:
            city = 'Искеле'
        district = p.get('district') or 'Long Beach'
        if district in ['', None, '']:
            district = 'Long Beach'
            
        line = f"""Объект {i}:
- Название: {p.get('title', 'Без названия')}
- Реальный тип объекта: {p_type} (НЕ вилла!)
- Реальный город: {city}
- Реальный район: {district} (НЕ Боаз!)
- Цена: {format_property_price(p, params)}
- Спален: {p.get('bedrooms', 'Не указано')}
- Площадь: {p.get('area_m2', 'Не указана')} м²
- Описание от владельца: {(p.get('description') or 'Нет описания')[:200]}
"""
        lines.append(line)
    return "\n".join(lines)


def _format_criteria(params: dict) -> str:
    """Форматирует критерии в текст."""
    parts = []
    if params.get('city'):
        parts.append(f"Город: {params['city']}")
    if params.get('property_type'):
        parts.append(f"Тип: {params['property_type']}")
    if params.get('listing_type'):
        parts.append(f"Сделка: {'покупка' if params['listing_type'] == 'sale' else 'аренда'}")
    if params.get('booking_start_date') and params.get('booking_end_date'):
        parts.append(f"Даты заезда: {params['booking_start_date']} — {params['booking_end_date']} (посуточная аренда)")
    if params.get('budget_min') or params.get('budget_max'):
        parts.append(f"Бюджет: {params.get('budget_min', '?')} - {params.get('budget_max', '?')}")
    if params.get('bedrooms'):
        parts.append(f"Спален: {params['bedrooms']}")
    return "\n".join(parts) if parts else "Не указаны"
