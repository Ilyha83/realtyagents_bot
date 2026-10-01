# -*- coding: utf-8 -*-
"""
coordinator.py — Координатор: принимает сообщение, определяет намерение,
направляет нужному агенту.
"""

from tools.llm import ask_llm
import json

COORDINATOR_PROMPT = """Ты — координатор команды AI-агентов для агентства недвижимости на Северном Кипре.
Твоя задача — понять намерение клиента и направить запрос нужному агенту.

Определи одно из следующих намерений (intent):

1. "greeting" — приветствие, знакомство, вопрос "что ты умеешь"
2. "search" — клиент ПРЯМО просит найти, показать, подобрать варианты или прислать список объектов (например: "покажи квартиры", "сделай подборку", "найди мне виллу", "какие есть варианты"). Если клиент просто отвечает на вопрос риелтора или описывает свои пожелания (например: "хочу снять на 2 недели", "мой бюджет 100 тысяч", "купить для инвестиций"), это НЕ "search", это "info".
3. "analytics" — клиент спрашивает о ценах на рынке, трендах, статистике
4. "info" — клиент задает вопрос про конкретный район/закон, оставляет свои контакты, либо просто отвечает на вопросы Лид-Менеджера о своих предпочтениях (бюджет, тип сделки, срок, цели).
5. "content" — нужно создать описание объекта, пост, рекламу
6. "other" — не относится к недвижимости

Также извлеки параметры поиска если они есть (учти, что текущий год — 2026):
- city (город: Кирения/Kyrenia, Фамагуста/Famagusta, Искеле/Iskele, Никосия/Nicosia, Гюзельюрт/Guzelyurt, Лефке/Lefke, Газиверен/Gaziveren)
- property_type (тип: квартира/apartment, вилла/villa, пентхаус/penthouse, участок/land, дом/house. Если клиент назвал несколько типов, например "вилла или пентхаус", укажи через запятую: "villa, penthouse")
- listing_type (sale, rent или null, если тип сделки явно не указан)
- budget_min, budget_max (бюджет, числом. Если указано "до 80 евро", "100 евро в сутки", "300 евро" — укажи именно эту цифру, например budget_max: 80, а НЕ умножай на 1000! Если клиент говорит "любой", "без ограничений", "не важно" — укажи budget_max: 999999)
- bedrooms, bedrooms_min, bedrooms_max (количество спален: студия -> 0; 1+1 -> 1; 2+1 -> 2; 3+1 -> 3. Если клиент указал несколько вариантов, например "1+1 и 2+1" -> bedrooms_min: 1, bedrooms_max: 2, bedrooms: 1; "студия или 1+1" -> bedrooms_min: 0, bedrooms_max: 1; "от 2 спален" -> bedrooms_min: 2, bedrooms_max: null; "1+1" -> bedrooms_min: 1, bedrooms_max: 1, bedrooms: 1)
- booking_start_date (дата заезда, в формате YYYY-MM-DD или null)
- booking_end_date (дата выезда, в формате YYYY-MM-DD или null)

⚠️ **ПРАВИЛО НЕ-ДОДУМЫВАНИЯ (КРИТИЧЕСКИ ВАЖНО):**
*   **Запрещено угадывать или додумывать параметры!** Если в тексте сообщения пользователя явно не указана покупка (купить, приобрести, продажа) или аренда (снять, арендовать, пожить, посуточно, сутки), параметр `listing_type` обязан быть строго `null`.
*   Если в тексте нет названия города/района — параметр `city` обязан быть строго `null`. Ни в коем случае не пиши строку "null", а передавай реальный null (None).
*   Если в тексте явно не указан тип недвижимости (квартира, апартаменты, вилла, пентхаус, студия, дом) — параметр `property_type` обязан быть строго `null`! Запрещено выдумывать "house, land" или любой другой тип.

Ответь СТРОГО в формате JSON:
{
  "intent": "...",
  "params": {
    "city": null,
    "property_type": null,
    "listing_type": null, // строго null, если не указано явно "купить" или "снять"
    "budget_min": null,
    "budget_max": null,
    "bedrooms": null,
    "bedrooms_min": null,
    "bedrooms_max": null,
    "booking_start_date": null,
    "booking_end_date": null
  },
  "summary": "краткое описание запроса клиента на русском"
}
"""


import json
import re
from tools.llm import ask_llm
from tools.dates import extract_booking_dates


def parse_bedrooms(text: str):
    """
    Извлекает количество спален из текста пользователя.
    Возвращает (bedrooms_min, bedrooms_max, bedrooms_list).
    """
    t = text.lower().strip()

    # Защита от дат: если в сообщении даты и нет явных слов о спальнях/гостях, не парсить как спальни
    has_date_indicators = any(mon in t for mon in ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек", "cент", "числа", "чисел"])
    has_explicit_beds = any(w in t for w in ["спал", "комнат", "+1", "1+0", "однушк", "двушк", "трешк", "студи", "studio", "гост", "человек", "взросл", "семья"])

    if has_date_indicators and not has_explicit_beds:
        return None, None, []

    # Диапазоны: 'от 1 до 2 спален', '1-2 спальни', '1-2+1' (обязателен маркер спален или +1)
    m_range = re.search(r'(?:от\s*)?([0-4])\s*(?:-|до)\s*([0-4])\s*(?:спал|комнат|\+1)', t)
    if m_range:
        b1, b2 = int(m_range.group(1)), int(m_range.group(2))
        return min(b1, b2), max(b1, b2), list(range(min(b1, b2), max(b1, b2) + 1))

    # 'от X спален', 'от X+1'
    m_from = re.search(r'(?:от|минимум)\s*([0-4])\s*(?:спал|комнат|\+1)', t)
    if m_from:
        b = int(m_from.group(1))
        return b, None, [b]

    # 'до X спален', 'до X+1'
    m_to = re.search(r'(?:до|максимум)\s*([0-4])\s*(?:спал|комнат|\+1)', t)
    if m_to:
        b = int(m_to.group(1))
        return 0, b, list(range(0, b + 1))

    found = set()
    for m in re.finditer(r'([0-9])\s*\+\s*1', t):
        found.add(int(m.group(1)))

    if '1+0' in t or 'студи' in t or 'studio' in t:
        found.add(0)

    if 'однушк' in t:
        found.add(1)
    if 'двушк' in t:
        found.add(2)
    if 'трешк' in t:
        found.add(3)

    m_multi = re.search(r'((?:[0-9]\s*(?:,|и|или)\s*)+[0-9])\s*(?:спал|комн|bed)', t)
    if m_multi:
        for d in re.findall(r'[0-9]', m_multi.group(1)):
            found.add(int(d))

    for m in re.finditer(r'([0-9])\s*(?:спал|комн|bed)', t):
        found.add(int(m.group(1)))

    if not found and not has_date_indicators:
        if any(w in t for w in ['один', 'одна', 'вдвоем', 'двое', 'паро', 'пара', 'паре', 'пару', 'с девушк', 'с жен', 'с муж']):
            found.add(1)
        elif any(w in t for w in ['трое', 'троих', 'ребенк', 'детьм', 'семья с']):
            found.add(2)
        elif t in ['0', '1', '2', '3', '4', '5']:
            found.add(int(t))

    if found:
        s = sorted(list(found))
        return s[0], s[-1], s

    return None, None, []


def fast_deterministic_classify(user_message: str) -> dict | None:
    """
    Мгновенная (0мс) детерминированная классификация намерения и параметров.
    Предотвращает зависания бота и исключает сбои при сетевых тайм-аутах LLM.
    """
    t = user_message.lower().strip()

    # 1. Приветствия
    greetings = ["привет", "здравствуй", "добрый день", "добрый вечер", "доброе утро", "салам", "хай", "hello", "hi"]
    if any(re.search(r'\b' + re.escape(g), t) for g in greetings) and len(t.split()) <= 4:
        return {"intent": "greeting", "params": {}, "summary": user_message}

    # 2. Аналитика
    analytics_words = ["аналитик", "динамик цен", "статистик", "рынок", "сколько стоит метр", "внж", "налог 9", "титул эшдегер"]
    if any(w in t for w in analytics_words) and not any(w in t for w in ["снять", "аренд"]):
        return {"intent": "analytics", "params": {}, "summary": user_message}

    # 3. Контент
    content_words = ["напиши пост", "составь объявление", "сделай пост", "рекламный текст", "создать объявление"]
    if any(w in t for w in content_words):
        return {"intent": "content", "params": {}, "summary": user_message}

    # 4. Извлечение параметров недвижимости
    params = {
        "city": None,
        "property_type": None,
        "listing_type": None,
        "budget_min": None,
        "budget_max": None,
        "bedrooms": None,
        "bedrooms_min": None,
        "bedrooms_max": None,
        "bedrooms_list": None,
        "booking_start_date": None,
        "booking_end_date": None
    }

    # Город
    if any(w in t for w in ["кирени", "girne", "kyrenia", "гирне", "алсанджак", "лапта", "эсентепе"]):
        params["city"] = "Кирения"
    elif any(w in t for w in ["искеле", "iskele", "long beach", "лонг бич", "боаз", "богаз"]):
        params["city"] = "Искеле"
    elif any(w in t for w in ["фамагуст", "famagusta", "гасимагус", "magusa"]):
        params["city"] = "Фамагуста"
    elif any(w in t for w in ["никоси", "nicosia", "лефкош", "lefkosa"]):
        params["city"] = "Никосия"
    elif any(w in t for w in ["гюзел", "guzelyurt", "морфу", "morphou", "лефке", "lefke", "газиверен", "gaziveren"]):
        params["city"] = "Гюзельюрт"

    # Тип недвижимости
    prop_type_words = {
        "villa": ["вилл", "villa", "коттедж", "таунхаус"],
        "penthouse": ["пентхаус", "penthouse"],
        "apartment": ["квартир", "апартамент", "apart", "flat"],
        "studio": ["студи", "studio"],
        "house": [" дом", "дома", "доме", "домик", "house"]
    }
    p_types = [pt for pt, kws in prop_type_words.items() if any(w in t for w in kws)]
    if p_types:
        params["property_type"] = ", ".join(p_types)

    # Тип сделки
    rent_kws = [
        "аренд", "сним", "снять", "посут", "сутк", "суточ", "пожит", "пожив",
        "недел", "недельк", "попробовать пожить", "остановит", "отпуск", "rent"
    ]
    sale_kws = ["куп", "покуп", "приобре", "инвест", "выкуп", "buy", "sale"]
    if any(k in t for k in rent_kws):
        params["listing_type"] = "rent"
    elif any(k in t for k in sale_kws):
        params["listing_type"] = "sale"

    # Спальни
    b_min, b_max, b_list = parse_bedrooms(user_message)
    if b_min is not None:
        params["bedrooms_min"] = b_min
        params["bedrooms_max"] = b_max
        params["bedrooms"] = b_min
        params["bedrooms_list"] = b_list

    # Бюджет
    # Проверка на просто число (например "80", "100", "70")
    t_clean = t.strip()
    if t_clean.isdigit() and int(t_clean) >= 20 and not (20 <= int(t_clean) <= 31 and any(mon in t for mon in ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"])):
        params["budget_max"] = float(t_clean)
    else:
        m1 = re.search(r'(?:до|около|бюджет\s*(?:до)?|тогда|пусть|ну|максимум)?\s*(\d+[\d\s]*)\s*(?:тыс|тысяч|[кk])?\s*(?:фунт|евро|eur|€|\$|долл|gbp|лир)?', t)
        if m1 and m1.group(1).strip():
            s = m1.group(1).replace(' ', '')
            if s.isdigit():
                val = float(s)
                if any(k in m1.group(0) for k in ['тыс', 'тысяч', 'к', 'k']):
                    val *= 1000
                if val >= 20 and not (20 <= val <= 31 and any(mon in t for mon in ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"])):
                    params["budget_max"] = val
        elif any(w in t for w in ["любой", "без разниц", "не важно", "без огранич"]):
            params["budget_max"] = 999999

    # Даты бронирования
    b_s, b_e = extract_booking_dates(user_message)
    if b_s and b_e:
        params["booking_start_date"] = b_s
        params["booking_end_date"] = b_e

    # Определение намерения
    search_triggers = ["что есть", "какие есть", "покажи", "найди", "подбери", "вариант", "предложи", "список"]
    if any(w in t for w in search_triggers):
        return {"intent": "search", "params": params, "summary": user_message}
    elif any(v is not None for v in params.values()):
        return {"intent": "info", "params": params, "summary": user_message}

    return None


async def classify_intent(user_message: str) -> dict:
    """
    Определяет намерение пользователя и извлекает параметры.
    Сначала проверяет мгновенный детерминированный слой (0мс),
    при необходимости обращается к LLM с гарантированным фоллбэком.

    Returns:
        dict с ключами: intent, params, summary
    """
    # 1. Быстрый детерминированный путь
    fast_res = fast_deterministic_classify(user_message)
    if fast_res is not None:
        return fast_res

    # 2. Обращение к LLM для нестандартных или сложных запросов
    try:
        response = await ask_llm(
            system_prompt=COORDINATOR_PROMPT,
            user_message=user_message,
            temperature=0.1,
            max_tokens=512,
        )

        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)

        if "intent" not in result:
            result["intent"] = "other"
        if "params" not in result or not isinstance(result["params"], dict):
            result["params"] = {}
        if "summary" not in result:
            result["summary"] = user_message

        # Санитизация параметров
        params = result["params"]
        for k, v in list(params.items()):
            if isinstance(v, str) and v.strip().lower() in ["null", "none", "undefined", ""]:
                params[k] = None

        return result

    except Exception:
        # Безопасный фоллбэк при тайм-ауте или ошибке LLM
        return {
            "intent": "other",
            "params": {},
            "summary": user_message,
        }
