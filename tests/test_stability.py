# -*- coding: utf-8 -*-
"""
test_stability.py — Стресс-тест стабильности и изоляции Цифрового АН.
Проверяет:
1. Активацию WAL-режима и конкурентный доступ (10 асинхронных писателей + 5 синхронных читателей).
2. Безопасность синхронных соединений get_sync_db().
3. Отказоустойчивость ask_llm с механизмом Retry.
4. Бесперебойное формирование аналитических отчетов рынка.
"""

import sys
import os
import asyncio
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.database import init_db, get_sync_db, log_interaction, get_or_create_client, DB_PATH
from tools.llm import ask_llm
from agents.market_analyst import build_market_overview_report, get_macro_period_report


async def async_writer(worker_id: int, count: int = 5):
    """Асинхронная запись взаимодействий в базу."""
    for i in range(count):
        await log_interaction(
            client_id=1,
            agent_name=f"Worker_{worker_id}",
            action="stress_test",
            details=f"Stress write #{i} from worker {worker_id}"
        )
        await asyncio.sleep(0.01)


def sync_reader(reader_id: int, results: list):
    """Синхронное чтение из базы параллельно с асинхронной записью."""
    try:
        conn = get_sync_db(timeout=10.0)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM properties")
        cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM interactions")
        interactions_cnt = c.fetchone()[0]
        conn.close()
        results.append(True)
    except Exception as e:
        print(f"❌ Reader {reader_id} error: {e}")
        results.append(False)


async def test_db_concurrency_and_wal():
    """Тест 1: Конкурентный стресс-тест SQLite WAL."""
    print("▶ Тест 1: Проверка SQLite WAL и конкурентного доступа...")
    await init_db()

    # Проверяем journal_mode
    conn = get_sync_db()
    c = conn.cursor()
    c.execute("PRAGMA journal_mode")
    mode = c.fetchone()[0].lower()
    conn.close()
    assert mode == "wal", f"Ожидался journal_mode=wal, получено: {mode}"
    print("  ✅ Режим WAL успешно активирован!")

    # Запускаем 10 асинхронных писателей
    writer_tasks = [async_writer(i, count=5) for i in range(10)]

    # И параллельно 5 синхронных читателей в потоках
    sync_results = []
    threads = [threading.Thread(target=sync_reader, args=(i, sync_results)) for i in range(5)]
    for t in threads:
        t.start()

    await asyncio.gather(*writer_tasks)

    for t in threads:
        t.join()

    assert all(sync_results), "Один или несколько читателей упали с ошибкой блокировки!"
    print("  ✅ 10 одновременных писателей и 5 читателей отработали без единой блокировки!")


async def test_llm_live():
    """Тест 2: Проверка LLM с механизмом Retry."""
    print("▶ Тест 2: Проверка LLM и механизма повторных попыток...")
    res = await ask_llm(
        system_prompt="Ответь одним словом.",
        user_message="Скажи 'СТАБИЛЬНОСТЬ'",
        retries=2
    )
    assert len(res) > 0 and "Извините" not in res, f"Неожиданный ответ LLM: {res}"
    print(f"  ✅ LLM ответил успешно: '{res[:30]}...'")


def test_market_reports():
    """Тест 3: Формирование макро-отчетов рынка без падений."""
    print("▶ Тест 3: Формирование аналитических отчетов...")
    overview = build_market_overview_report()
    assert "АНАЛИТИЧЕСКИЙ ОБЗОР РЫНКА" in overview, "Ошибка структуры обзора рынка"

    period_rep = get_macro_period_report("1m")
    assert "АНАЛИТИКА СПРОСА" in period_rep or "ПОСЛЕДНИЙ МЕСЯЦ" in period_rep, "Ошибка структуры отчета за период"
    print("  ✅ Аналитические отчеты формируются мгновенно и без сбоев!")


async def main():
    print("=" * 60)
    print("🚀 СТРЕСС-ТЕСТИРОВАНИЕ СТАБИЛЬНОСТИ «ЦИФРОВОГО АН»")
    print("=" * 60)
    await test_db_concurrency_and_wal()
    await test_llm_live()
    test_market_reports()
    print("=" * 60)
    print("🎉 ВСЕ ТЕСТЫ СТАБИЛЬНОСТИ ПРОЙДЕНЫ УСПЕШНО!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
