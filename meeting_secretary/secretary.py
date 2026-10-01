# -*- coding: utf-8 -*-
"""
secretary.py — Модуль AI-Протоколиста Планёрок и Совещаний.
Анализирует стенограммы встреч, формирует задачи, решения и аналитику участников.
"""

import os
import json
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(
    api_key=os.getenv("NVIDIA_API_KEY"),
    base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
)
MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")


MEETING_PROMPT = """Ты — высококлассный AI-Протоколист и бизнес-аналитик совещаний.
Тебе предоставляется стенограмма внутренней планёрки/совещания компании (разговор нескольких спикеров).

Твоя задача — извлечь максимум пользы и сформировать чёткий протокол встречи.

Сформируй ответ СТРОГО в формате JSON:
{
  "meeting_title": "Тема или название планёрки",
  "summary": "Главное резюме встречи в 2-3 предложениях",
  "key_decisions": [
    "Список конкретных решений, которые были ПРИНЯТЫ на встрече"
  ],
  "action_items": [
    {
      "assignee": "Имя ответственного",
      "task": "Конкретная задача, что сделать",
      "deadline": "Срок выполнения (если озвучен, иначе 'Не указан')"
    }
  ],
  "stuck_topics": [
    "Темы, которые обсуждались, но по которым НЕ БЫЛО принято решения (зависли / отложены)"
  ],
  "participants_kpi": [
    {
      "name": "Имя участника",
      "role_summary": "Краткая роль на встрече и вклад (например: 'Активно предлагал решения', 'Пассивно молчал', 'Задавал вопросы')"
    }
  ],
  "efficiency_score": 85
}
"""


async def process_meeting_transcript(transcript: str, title: str = "Еженедельная планёрка") -> dict:
    """
    Анализирует стенограмму планёрки.

    Args:
        transcript: Текст записи совещания
        title: Название встречи

    Returns:
        dict с протоколом встречи
    """
    user_msg = f"Тема встречи: {title}\n\nСтенограмма планёрки:\n{transcript}"

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": MEETING_PROMPT},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.2,
            max_tokens=2500
        )

        content = response.choices[0].message.content.strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return json.loads(content)

    except Exception as e:
        print(f"❌ Ошибка обработки планёрки: {e}")
        return {"error": str(e)}
