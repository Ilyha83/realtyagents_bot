# -*- coding: utf-8 -*-
"""
demo.py — Демонстрационный запуск AI-Meeting Secretary.
Анализирует планёрку руководства и генерирует протокол решений и задач.
"""

import os
import sys
import asyncio
from secretary import process_meeting_transcript

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def render_meeting_protocol(data: dict):
    """Отрисовывает протокол встречи."""
    print("=" * 75)
    print("📋 ПРОТОКОЛ СОВЕЩАНИЯ / ПЛАНЁРКИ")
    print("=" * 75)

    if "error" in data:
        print(f"❌ Ошибка: {data['error']}")
        return

    title = data.get("meeting_title", "Планёрка")
    summary = data.get("summary", "")
    score = data.get("efficiency_score", 0)

    print(f"📌 Тема: {title}")
    print(f"⚡ Эффективность встречи: {score}%")
    print(f"📖 Главное резюме: {summary}\n")

    print("✅ ПРИНЯТЫЕ РЕШЕНИЯ:")
    decisions = data.get("key_decisions", [])
    for idx, d in enumerate(decisions, 1):
        print(f"  {idx}. {d}")

    print("\n🎯 ПОРУЧЕНИЯ И ЗАДАЧИ (ACTION ITEMS):")
    actions = data.get("action_items", [])
    for a in actions:
        who = a.get("assignee", "Не указан")
        task = a.get("task", "")
        dl = a.get("deadline", "Без срока")
        print(f"  👤 {who:<15} ➔ {task} (⏰ Срок: {dl})")

    stuck = data.get("stuck_topics", [])
    if stuck:
        print("\n⚠️ ЗАВИСШИЕ / ОТЛОЖЕННЫЕ ВОПРОСЫ (БЕЗ РЕШЕНИЯ):")
        for s in stuck:
            print(f"  ⏳ {s}")

    kpi = data.get("participants_kpi", [])
    if kpi:
        print("\n👥 ВКЛАД УЧАСТНИКОВ ВСТРЕЧИ:")
        for p in kpi:
            name = p.get("name", "")
            role_sum = p.get("role_summary", "")
            print(f"  • {name:<18}: {role_sum}")

    print("\n" + "=" * 75 + "\n")


async def main():
    base_dir = os.path.dirname(__file__)
    from generate_html import create_meeting_html
    file_path = os.path.join(base_dir, 'samples', 'sample_meeting.txt')

    with open(file_path, 'r', encoding='utf-8') as f:
        transcript = f.read()

    print("🚀 Запуск AI-Протоколиста планёрки...")
    protocol = await process_meeting_transcript(transcript, title="Еженедельная стратегическая планёрка")
    render_meeting_protocol(protocol)
    create_meeting_html(protocol, "report_meeting_protocol.html")


if __name__ == "__main__":
    asyncio.run(main())
