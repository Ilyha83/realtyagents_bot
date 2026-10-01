# -*- coding: utf-8 -*-
"""
demo.py — Демонстрационный запуск AI-Sales Auditor.
Проводит аудит телефонного звонка и переписки из WhatsApp, выводит наглядный отчёт.
"""

import os
import sys
import asyncio
from auditor import audit_communication

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def render_report(report: dict, title: str):
    """Выводит отчёт аудита в консоль в форматированном виде."""
    print("=" * 70)
    print(f"📊 {title.upper()}")
    print("=" * 70)

    if "error" in report:
        print(f"❌ Ошибка аудита: {report['error']}")
        return

    manager = report.get("manager_name", "Не указан")
    score = report.get("overall_score_percent", 0)
    comm_type = report.get("communication_type", "коммуникация")
    summary = report.get("summary", "")

    # Оценка цвета/эмодзи
    status_emoji = "🟢" if score >= 80 else ("🟡" if score >= 60 else "🔴")

    print(f"👤 Менеджер: {manager}")
    print(f"📱 Тип: {comm_type.capitalize()}")
    print(f"{status_emoji} Итоговый показатель KPI: {score}%")
    print(f"📝 Резюме: {summary}\n")

    print("🎯 ОЦЕНКИ ПО КРИТЕРИЯМ (0-10):")
    criteria = report.get("criteria_scores", {})
    labels = {
        "greeting": "1. Приветствие и контакт",
        "initiative": "2. Инициатива и ведение диалога",
        "needs_discovery": "3. Выявление потребностей",
        "presentation": "4. Презентация решения",
        "objections_handling": "5. Отработка возражений",
        "compliance": "6. Соблюдение стандартов/скорость",
        "closing_next_step": "7. Закрытие на следующий шаг"
    }

    for key, label in labels.items():
        data = criteria.get(key, {})
        c_score = data.get("score", 0)
        c_comment = data.get("comment", "")
        bar = "█" * c_score + "░" * (10 - c_score)
        print(f"  {label:<35} [{bar}] {c_score}/10 — {c_comment}")

    violations = report.get("critical_violations", [])
    if violations:
        print("\n⚠️ НАРУШЕНИЯ И ОШИБКИ:")
        for v in violations:
            print(f"  ❌ {v}")

    recommendations = report.get("recommendations", [])
    if recommendations:
        print("\n💡 РЕКОМЕНДАЦИИ ДЛЯ ПОВЫШЕНИЯ ПРОДАЖ:")
        for r in recommendations:
            print(f"  👉 {r}")

    print("\n" + "=" * 70 + "\n")


async def main():
    base_dir = os.path.dirname(__file__)
    from generate_html import create_auditor_html

    # 1. Читаем звонок
    call_file = os.path.join(base_dir, 'samples', 'sample_call.txt')
    with open(call_file, 'r', encoding='utf-8') as f:
        call_text = f.read()

    print("🚀 [1/2] Запуск AI-Аудита телефонного звонка менеджера Алексея...")
    call_report = await audit_communication(call_text, comm_type="телефонный звонок")
    render_report(call_report, "Аудит телефонного звонка (Недвижимость)")
    create_auditor_html(call_report, "report_sales_call.html")

    # 2. Читаем чат WhatsApp
    chat_file = os.path.join(base_dir, 'samples', 'sample_chat.txt')
    with open(chat_file, 'r', encoding='utf-8') as f:
        chat_text = f.read()

    print("🚀 [2/2] Запуск AI-Аудита переписки WhatsApp менеджера Дмитрия...")
    chat_report = await audit_communication(chat_text, comm_type="переписка WhatsApp")
    render_report(chat_report, "Аудит переписки WhatsApp (IT-Курсы)")
    create_auditor_html(chat_report, "report_sales_chat.html")


if __name__ == "__main__":
    asyncio.run(main())
