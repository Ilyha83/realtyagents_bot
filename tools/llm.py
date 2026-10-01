# -*- coding: utf-8 -*-
"""
llm.py — Подключение к NVIDIA LLM API (OpenAI-совместимый).
"""

import os
import sys
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

_client = None


def get_llm_client() -> AsyncOpenAI:
    """Возвращает клиент NVIDIA API."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=os.getenv("NVIDIA_API_KEY"),
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            timeout=15.0,
        )
    return _client


async def ask_llm(
    system_prompt: str,
    user_message: str,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    retries: int = 3,
) -> str:
    """
    Отправляет запрос к LLM и возвращает текстовый ответ с автоматическими повторными попытками.
    """
    client = get_llm_client()
    model = model or os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")

    backoff = 1.0
    for attempt in range(1, retries + 1):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            if attempt < retries:
                print(f"⚠️ [LLM RETRY {attempt}/{retries}] Ошибка ({e}). Повтор через {backoff:.1f}с...")
                await asyncio.sleep(backoff)
                backoff *= 2.0
            else:
                print(f"❌ [LLM FINAL ERROR] Все {retries} попыток исчерпаны: {e}")

    return "Извините, произошла ошибка при обработке запроса. Попробуйте позже."


async def ask_llm_with_history(
    system_prompt: str,
    messages: list,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    retries: int = 3,
) -> str:
    """
    Отправляет запрос с историей диалога с автоматическими повторными попытками.

    Args:
        system_prompt: Системный промпт.
        messages: Список сообщений [{"role": "user/assistant", "content": "..."}].
        model: Модель.
        temperature: Креативность.
        max_tokens: Максимум токенов.
        retries: Количество попыток.

    Returns:
        Текстовый ответ модели.
    """
    client = get_llm_client()
    model = model or os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    backoff = 1.0
    for attempt in range(1, retries + 1):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            if attempt < retries:
                print(f"⚠️ [LLM RETRY {attempt}/{retries}] Ошибка ({e}). Повтор через {backoff:.1f}с...")
                await asyncio.sleep(backoff)
                backoff *= 2.0
            else:
                print(f"❌ [LLM FINAL ERROR] Все {retries} попыток исчерпаны: {e}")

    return "Извините, произошла ошибка. Попробуйте позже."
