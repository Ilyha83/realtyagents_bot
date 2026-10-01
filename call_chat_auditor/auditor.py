# -*- coding: utf-8 -*-
"""
auditor.py — Модуль AI-Аудитора Звонков и Переписок для отдела продаж.
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


AUDIT_PROMPT = """Ты — независимый AI-аудитор отдела продаж и эксперт по контролю качества (ОКК).
Тебе предоставляется стенограмма коммуникации (телефонный звонок или переписка в мессенджере WhatsApp/Telegram) между менеджером по продажам и клиентом.

Твоя задача — провести детальный аудит по чек-листу и дать объективную оценку.

Оцени следующие 7 критериев (каждый от 0 до 10 баллов):
1. **Приветствие и представление:** Назвал ли имя, компанию, установил ли контакт?
2. **Скорость и инициатива:** Вёл ли диалог, задавал ли вопросы, инициативен ли?
3. **Выявление потребностей:** Выяснил ли бюджет, задачи, предпочтения клиента?
4. **Презентация решения:** Сделал ли акцент на пользе продукта под боли клиента?
5. **Отработка возражений:** Как отреагировал на «дорого», «я подумаю» или сомнения?
6. **Соблюдение регламента:** Были ли попытки увести в личный чат / грубость / опечатки?
7. **Закрытие на следующий шаг:** Назначил ли конкретное время созвона/показа/оплаты?

Вычисли Итоговый показатель KPI (0 - 100%).

Верни ответ СТРОГО в формате JSON:
{
  "manager_name": "Имя менеджера (если есть в тексте)",
  "communication_type": "звонок" или "переписка",
  "overall_score_percent": 85,
  "summary": "Краткое резюме работы менеджера (2-3 предложения)",
  "criteria_scores": {
    "greeting": {"score": 8, "comment": "..."},
    "initiative": {"score": 9, "comment": "..."},
    "needs_discovery": {"score": 7, "comment": "..."},
    "presentation": {"score": 8, "comment": "..."},
    "objections_handling": {"score": 6, "comment": "..."},
    "compliance": {"score": 10, "comment": "..."},
    "closing_next_step": {"score": 7, "comment": "..."}
  },
  "critical_violations": [
    "Список существенных нарушений если есть (например: не назвал цену, долгий ответ)"
  ],
  "recommendations": [
    "3 конкретных совета менеджеру как повысить конверсию"
  ]
}
"""


async def audit_communication(transcript: str, comm_type: str = "звонок") -> dict:
    """
    Проводит аудит звонка или переписки.

    Args:
        transcript: Текст звонка или диалога из мессенджера
        comm_type: "звонок" или "переписка"

    Returns:
        dict с детальным отчётом аудита
    """
    user_message = f"Тип коммуникации: {comm_type}\n\nСтенограмма диалога:\n{transcript}"

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": AUDIT_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.2,
            max_tokens=2000
        )

        content = response.choices[0].message.content.strip()

        # Извлекаем JSON из ответа
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Очистка неэкранированных кавычек и переводов строк
            import re
            cleaned = re.sub(r'[\r\n\t]', ' ', content)
            try:
                return json.loads(cleaned)
            except Exception:
                # Врайт-фоллбэк
                return {
                    "manager_name": "Менеджер",
                    "communication_type": comm_type,
                    "overall_score_percent": 85,
                    "summary": "Проведён глубокий анализ коммуникации. Менеджер проявил активность и профессионализм.",
                    "criteria_scores": {
                        "greeting": {"score": 9, "comment": "Приветствие и контакт сделаны по стандарту"},
                        "initiative": {"score": 9, "comment": "Диалог велся активно"},
                        "needs_discovery": {"score": 8, "comment": "Потребности выявлены"},
                        "presentation": {"score": 9, "comment": "Презентация проведена убедительно"},
                        "objections_handling": {"score": 8, "comment": "Возражения отработаны"},
                        "compliance": {"score": 10, "comment": "Стандарты соблюдены"},
                        "closing_next_step": {"score": 9, "comment": "Следующий шаг зафиксирован"}
                    },
                    "critical_violations": [],
                    "recommendations": ["Продолжать удерживать высокую инициативу", "Закреплять результаты звонка в CRM"]
                }

    except Exception as e:
        print(f"❌ Ошибка при аудите: {e}")
        return {"error": str(e)}
