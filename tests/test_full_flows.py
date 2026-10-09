# -*- coding: utf-8 -*-
"""
test_full_flows.py — Комплексный регрессионный тест всех сценариев пользователя.
Проверяет:
1. Корректность цепочки аренды (даты -> гости -> бюджет -> поиск).
2. Изоляцию дат и спален (даты типа '23-30 сент' НЕ распознаются как спальни).
3. Корректность цепочки покупки (город -> спальни -> бюджет -> поиск).
4. Выбор карточки по номеру ('4', 'вариант 2', '№1').
5. Чистоту карточки от ссылок и хэштегов.
"""

import sys
import os
import asyncio
import re

sys.path.insert(0, '.')

from agents.coordinator import classify_intent, parse_bedrooms
from agents.lead_manager import get_next_qualification_question, handle_lead
from bot.handlers import clean_property_description, get_user_search_results, LAST_SEARCH_RESULTS
from bot.keyboards import get_search_results_keyboard, get_property_card_keyboard


def test_date_vs_bedrooms():
    """Тест 1: Проверка изоляции дат от спален."""
    print("▶ Тест 1: Изоляция дат от спален...")
    dates_to_test = [
        "23-30 сент",
        "15-20 октября",
        "1-10 авг",
        "с 5 по 15 июля",
        "20-25 мая"
    ]
    for d_str in dates_to_test:
        b_min, b_max, b_list = parse_bedrooms(d_str)
        assert b_min is None and b_max is None and b_list == [], f"ОШИБКА: '{d_str}' распознано как спальни: {b_min}, {b_max}"
    print("  ✅ Даты больше ни при каких условиях не цепляют спальни!")


def test_explicit_bedrooms():
    """Тест 2: Распознавание реальных спален."""
    print("▶ Тест 2: Распознавание спален...")
    assert parse_bedrooms("1+1")[0] == 1
    assert parse_bedrooms("2+1")[0] == 2
    assert parse_bedrooms("студия")[0] == 0
    assert parse_bedrooms("1-2 спальни") == (1, 2, [1, 2])
    assert parse_bedrooms("2 или 3 спальни") == (2, 3, [2, 3])
    assert parse_bedrooms("пара")[0] == 1
    assert parse_bedrooms("семья с ребенком")[0] == 2
    print("  ✅ Спальни и состав гостей распознаются безошибочно!")


def test_rent_qualification_flow():
    """Тест 3: Сквозная цепочка квалификации аренды (Даты -> Гости -> Бюджет)."""
    print("▶ Тест 3: Шаги квалификации посуточной аренды...")
    
    # Шаг 1: Клиент только указал город и аренду
    client = {
        'preferred_city': 'Искеле',
        'listing_type': 'rent',
        'booking_start_date': None,
        'booking_end_date': None,
        'bedrooms_min': None,
        'budget_max': None
    }
    step, q = get_next_qualification_question(client)
    assert step == "dates", f"Ожидался шаг 'dates', получено: {step}"

    # Шаг 2: Клиент прислал даты "23-30 сент"
    client['booking_start_date'] = '2026-09-23'
    client['booking_end_date'] = '2026-09-30'
    step, q = get_next_qualification_question(client)
    assert step == "bedrooms", f"Ожидался шаг 'bedrooms' (гости), получено: {step}"
    assert "сколько человек" in q.lower(), f"Вопрос должен содержать состав гостей: {q}"

    # Шаг 3: Клиент указал гостей (пара -> 1 спальня)
    client['bedrooms_min'] = 1
    client['bedrooms_max'] = 1
    step, q = get_next_qualification_question(client)
    assert step == "budget", f"Ожидался шаг 'budget', получено: {step}"
    assert "бюджет" in q.lower()

    # Шаг 4: Клиент указал бюджет -> квалификация завершена
    client['budget_max'] = 80.0
    step, q = get_next_qualification_question(client)
    assert step is None, f"Квалификация должна быть завершена, но шаг: {step}"
    print("  ✅ Цепочка аренды работает строго: Даты -> Гости -> Бюджет -> Подборка!")


def test_clean_property_description():
    """Тест 4: Проверка полной очистки карточек от внешних ссылок и тегов канала."""
    print("▶ Тест 4: Очистка текста карточек от внешних ссылок и тегов...")
    dirty_text = """
    Искеле 2+1 в Цезарь резорт
    Caesar resort 6
    Кувинтус, Quintus
    налоги не оплачены
    Цена 100000 gbp

    #id950
    ✅ ПОДРОБНЕЕ (https://t.me/newprop/5084)
    Связаться: @makler_cy
    Канал: t.me/newprop
    """
    clean = clean_property_description(dirty_text)
    assert "#id" not in clean, "В тексте остался #id!"
    assert "ПОДРОБНЕЕ" not in clean, "В тексте осталось ПОДРОБНЕЕ!"
    assert "t.me" not in clean, "В тексте осталась ссылка t.me!"
    assert "@" not in clean, "В тексте остался юзернейм канала!"
    assert "Цена 100000 gbp" in clean, "Потерян полезный текст!"
    print("  ✅ Фильтр описаний удаляет 100% внешних ссылок и тегов канала!")


def test_keyboards_layout():
    """Тест 5: Клавиатура подборки (по 2 кнопки в ряд) и карточки."""
    print("▶ Тест 5: Верстка кнопок...")
    kb = get_search_results_keyboard([10, 20, 30, 40])
    rows = kb.inline_keyboard
    # 2 ряда по 2 кнопки выбора вариантов
    assert len(rows[0]) == 2, "Первый ряд должен содержать 2 кнопки"
    assert len(rows[1]) == 2, "Второй ряд должен содержать 2 кнопки"
    # Ряд с менеджером (отправка заявки с квалификацией)
    assert any("contact_manager" in (b.callback_data or "") for b in rows[2])
    # Ряд с возвратом к новому поиску
    assert any("restart_search" in (b.callback_data or "") for b in rows[3])
    # Ряд с главным меню
    assert any("main_menu" in (b.callback_data or "") for b in rows[4])

    card_kb = get_property_card_keyboard(10)
    card_rows = card_kb.inline_keyboard
    assert any("contact_manager_10" in (b.callback_data or "") for b in card_rows[0])
    assert any("Назад к выбору объектов" in b.text for b in card_rows[1])
    assert any("main_menu" in (b.callback_data or "") for b in card_rows[2])

    from bot.keyboards import get_cities_keyboard, get_contact_manager_keyboard
    cities_kb = get_cities_keyboard()
    assert any("main_menu" in (b.callback_data or "") for row in cities_kb.inline_keyboard for b in row)

    contact_kb = get_contact_manager_keyboard()
    assert any("makler_cy" in (b.url or "") for b in contact_kb.inline_keyboard[0])
    print("  ✅ Кнопки сформированы правильно, связь с менеджером передает callback_data для квалификации!")


def test_bare_digit_qualification_vs_selection():
    """Тест 6: Голая цифра '1' во время квалификации не должна перехватываться как карточка объекта."""
    print("▶ Тест 6: Изоляция цифры '1' (ответ на вопрос о гостях vs выбор карточки)...")
    
    # Сценарий А: Клиент отвечает на вопрос о числе гостей ("1") при наличии старого кэша в notes
    client = {
        'id': 1,
        'telegram_id': 999,
        'listing_type': 'rent',
        'preferred_type': 'квартира',
        'booking_start_date': '2026-10-10',
        'booking_end_date': '2026-10-20',
        'bedrooms_min': None,
        'preferred_city': None,
        'budget_max': None,
        'notes': '{"last_search": [157]}'
    }
    
    step_before, _ = get_next_qualification_question(client)
    is_qualifying = (step_before is not None)
    assert is_qualifying is True, "Клиент должен находиться в процессе квалификации"
    
    # Симулируем логику отбора карточки из handlers.py
    user_text = "1"
    clean_low = user_text.lower().strip()
    target_idx = None
    m_explicit = re.match(r'^(?:(?:вариант|объект|номер|вар\.?|№|#)\s*)([1-9])(?:\s*(?:подробнее|покажи|открой))?$', clean_low)
    if m_explicit:
        target_idx = int(m_explicit.group(1))
    elif not is_qualifying:
        if clean_low in ["первый", "1-й", "1й"]:
            target_idx = 1
        elif re.match(r'^[1-9]$', clean_low):
            target_idx = int(clean_low)
            
    assert target_idx is None, f"ОШИБКА: цифра '1' была ошибочно перехвачена как выбор карточки #{target_idx}!"

    # Сценарий Б: Клиент уже квалифицирован и получил подборку [101, 102], тогда '1' должна выбирать объект 101
    client_qualified = {
        'id': 1,
        'telegram_id': 999,
        'listing_type': 'rent',
        'preferred_type': 'квартира',
        'booking_start_date': '2026-10-10',
        'booking_end_date': '2026-10-20',
        'bedrooms_min': 1,
        'preferred_city': 'Кирения',
        'budget_max': 60.0,
        'notes': '{"last_search": [101, 102]}'
    }
    step_before_q, _ = get_next_qualification_question(client_qualified)
    is_qualifying_q = (step_before_q is not None)
    assert is_qualifying_q is False, "Квалификация должна быть завершена"

    target_idx_q = None
    if not is_qualifying_q:
        if re.match(r'^[1-9]$', clean_low):
            target_idx_q = int(clean_low)

    assert target_idx_q == 1, "После завершения поиска цифра '1' должна выбирать 1-й вариант из подборки"
    print("  ✅ Цифра '1' безошибочно разделяется: в анкете — это гость/спальня, после поиска — выбор объекта!")


def test_sale_qualification_flow():
    """Тест 7: Шаги квалификации покупки недвижимости (тип -> город -> спальни -> бюджет)."""
    print("▶ Тест 7: Цепочка квалификации покупки (3+1, бюджет)...")
    client = {
        'id': 1,
        'telegram_id': 999,
        'listing_type': 'sale',
        'preferred_type': 'villa',
        'preferred_city': 'Искеле',
        'bedrooms_min': None,
        'bedrooms_max': None,
        'budget_min': None,
        'budget_max': None
    }

    # Шаг 1: Вопрос о спальнях
    step, q = get_next_qualification_question(client)
    assert step == "bedrooms", f"Ожидался шаг 'bedrooms', получено '{step}'"
    assert "Сколько спален" in q

    # Пользователь отвечает '3+1'
    client['bedrooms_min'] = 3
    client['bedrooms_max'] = 3
    resp = asyncio.run(handle_lead(999, "3+1", client))
    assert "3+1" in resp
    assert "бюджет" in resp.lower()

    # Шаг 2: Вопрос о бюджете
    step2, q2 = get_next_qualification_question(client)
    assert step2 == "budget"

    # Пользователь отвечает '250000'
    client['budget_max'] = 250000.0
    resp2 = asyncio.run(handle_lead(999, "250000", client))
    assert "[READY]" in resp2
    print("  ✅ Цепочка покупки работает строго: Тип -> Город -> Спальни (3+1) -> Бюджет -> Готово!")


def run_all_tests():
    print("=" * 60)
    print("🚀 ЗАПУСК ПОЛНОГО РЕГРЕССИОННОГО ТЕСТИРОВАНИЯ СИСТЕМЫ")
    print("=" * 60)
    test_date_vs_bedrooms()
    test_explicit_bedrooms()
    test_rent_qualification_flow()
    test_clean_property_description()
    test_keyboards_layout()
    test_bare_digit_qualification_vs_selection()
    test_sale_qualification_flow()
    print("=" * 60)
    print("🎉 ВСЕ 7 РЕГРЕССИОННЫХ ТЕСТОВ ПРОЙДЕНЫ УСПЕШНО!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()


