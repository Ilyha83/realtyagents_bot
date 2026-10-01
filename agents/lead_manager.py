# -*- coding: utf-8 -*-
"""
lead_manager.py — Агент-лидменеджер: квалифицирует клиентов,
отвечает на вопросы/возражения, собирает профиль без амнезии и галлюцинаций.
"""

import re
from tools.llm import ask_llm_with_history
from tools.database import update_client, log_interaction

LEAD_ANSWER_PROMPT = """Ты — виртуальный ассистент консультационной службы по недвижимости на Северном Кипре (ТРСК).
Команда и роли:
- Ты сам — виртуальный AI-помощник (бот-консультант).
- Твой руководитель и старший риелтор — Илья (@makler_cy).

Правила:
1. Если спрашивают «как его зовут?», «кто риелтор?», «кто старший риелтор?» — ответь, что старшего риелтора зовут Илья (@makler_cy).
2. Если спрашивают «как вас зовут?», «кто ты?», «как тебя зовут?» — ответь, что ты виртуальный ассистент команды Ильи (@makler_cy).
3. Кратко (строго 1-2 предложения) отвечай по существу на русском языке. Без английских слов.
4. Локации только в ТРСК: Кирения, Искеле, Фамагуста (никакого Южного Кипра!).
5. НЕ задавай никаких встречных вопросов в конце своего ответа (следующий вопрос квалификации будет добавлен автоматически).
6. Не называй конкретных цен или объектов из базы данных (ты отвечаешь только за общие правила, условия аренды, пляжи, инфраструктуру и процесс).
"""

# Хранилище историй диалогов (в памяти, для MVP)
_conversations: dict[int, list] = {}


def get_next_qualification_question(client_data: dict) -> tuple[str | None, str | None]:
    """
    Детерминированно определяет следующий шаг квалификации клиента.
    Возвращает (имя_шага, текст_вопроса).
    """
    listing_type = client_data.get('listing_type')

    # 1. Тип сделки
    if not listing_type:
        return (
            "listing_type",
            "Подскажите, вы планируете покупку недвижимости или аренду?"
        )

    if listing_type == 'rent':
        # 2. Даты поездки
        if not client_data.get('booking_start_date'):
            return (
                "dates",
                "Подскажите, на какие даты вы планируете поездку (заезд и выезд)? Я сразу проверю доступность свободных вариантов."
            )
        # 3. Состав гостей / спальни
        if client_data.get('bedrooms_min') is None:
            return (
                "bedrooms",
                "Подскажите, сколько человек будет проживать (один, пара или семья с детьми)?"
            )
        # 4. Город / локация
        if not client_data.get('preferred_city'):
            return (
                "city",
                "В каком городе или районе хотите остановиться (Кирения, Искеле, Фамагуста)?"
            )
        # 5. Бюджет
        if not client_data.get('budget_max') and not client_data.get('budget_min'):
            return (
                "budget",
                "Какой ориентировочный бюджет в сутки вы рассматриваете?"
            )

    elif listing_type == 'sale':
        # 2. Тип недвижимости
        if not client_data.get('preferred_type'):
            return (
                "property_type",
                "Какой тип недвижимости вас интересует: апартаменты (1+1, 2+1), вилла или пентхаус?"
            )
        # 3. Город / локация
        if not client_data.get('preferred_city'):
            return (
                "city",
                "В каком городе или районе ТРСК рассматриваете покупку (Кирения, Искеле, Фамагуста)?"
            )
        # 4. Спальни
        if client_data.get('bedrooms_min') is None:
            return (
                "bedrooms",
                "Сколько спален рассматриваете (студия, 1+1, 2+1, 3+1)?"
            )
        # 5. Бюджет
        if not client_data.get('budget_max') and not client_data.get('budget_min'):
            return (
                "budget",
                "Какой ориентировочный бюджет на покупку вы рассматриваете?"
            )

    return (None, None)


async def handle_lead(telegram_id: int, user_message: str, client_data: dict) -> str:
    """
    Обрабатывает сообщение клиента в режиме квалификации.
    """
    msg_low = user_message.strip().lower()

    # 0. Запрос связи с живым человеком / менеджером / риелтором
    def _is_human_request(text: str) -> bool:
        t = text.lower().strip()
        if any(q in t for q in ["как зовут", "кто так", "кто он", "кто вы", "кто ты", "как его", "как вас", "сколько", "почему", "не нуж", "без риелтор", "без менеджер"]):
            return False
        connect_verbs = ["позови", "позовите", "дай", "дайте", "соедини", "соедините", "переключи", "переключите", "свяжи", "свяжите", "связаться с", "поговорить с", "пообщаться с", "нужен", "хочу", "передайте"]
        roles = ["человек", "менеджер", "риелтор", "риэлтор", "оператор", "специалист", "сотрудник"]
        for role in roles:
            if any(f"{v} {role}" in t or f"{v} с {role}" in t or f"{v} живого" in t for v in connect_verbs):
                return True
        direct_actions = [
            "позвони мне", "позвоните мне", "перезвони", "перезвоните", "наберите мне",
            "свяжитесь со мной", "свяжись со мной", "позвонить мне"
        ]
        if any(a in t for a in direct_actions):
            return True
        standalone = ["человека", "менеджера", "риелтора", "оператора", "живой человек", "живого человека", "оператор"]
        if t in standalone:
            return True
        return False

    if _is_human_request(msg_low):
        return (
            "Конечно! Я уже передал ваш запрос нашему старшему риелтору Илье (@makler_cy). Он свяжется с вами прямо в Telegram в ближайшее время!\n\n"
            "📞 Вы также можете написать свой номер телефона для оперативного звонка или связи в WhatsApp."
        )

    # 0.1 Получение номера телефона
    clean_digits = re.sub(r'[^\d+]', '', user_message)
    if len(re.findall(r'\d', clean_digits)) >= 10 and not any(w in msg_low for w in ["до", "от", "евро", "долл", "фунт", "eur", "gbp"]):
        return f"Спасибо! Номер {user_message.strip()} сохранен. Старший риелтор Илья (@makler_cy) свяжется с вами в течение 10–15 минут!"

    # 1. Проверяем эмоциональное раздражение или мат
    swears = ["блять", "бля", "сука", "нахуй", "похуй", "заебал", "заебись", "пиздец", "тупой", "глупый", "инвалид", "алё", "ау"]
    is_frustrated = any(re.search(r'\b' + re.escape(w), msg_low) for w in swears) or "координатор упал" in msg_low

    step_name, next_q = get_next_qualification_question(client_data)

    # 2. Проверяем, задал ли клиент вопрос, обращение или возражение
    question_regexes = [
        r'\bпочему\b', r'\bзачем\b', r'\bкак\b', r'\bгде\b', r'\bкакие\b', r'\bкакой\b', r'\bкакая\b',
        r'\bсколько\b', r'\bа можно\b', r'\bа если\b', r'\bчто с\b', r'\bрасскажи\b',
        r'\bгаранти', r'\bдоговор', r'\bпаспорт', r'\bвиз', r'\bтрансфер', r'\bсобак', r'\bживотн',
        r'\bпляж', r'\bтитул', r'\bзовут\b', r'\bваше имя\b', r'\bего имя\b',
        r'\bкто ты\b', r'\bкто он\b', r'\bкто вы\b', r'\bкто старший\b', r'\bкто риелтор\b', r'\bкто такой\b',
        r'\bкогда напишет\b', r'\bкогда свяжется\b'
    ]
    general_inquiry_words = [
        "предложить", "предложите", "предложишь", "что есть", "какие есть",
        "какие варианты", "покажите", "показать", "подобрать", "подберите",
        "варианты", "посмотреть", "посоветуете", "посоветуй", "подыскать"
    ]
    is_general_inquiry = any(k in msg_low for k in general_inquiry_words)
    has_question_mark = "?" in user_message and len(user_message.strip()) > 3
    has_word_question = any(re.search(r, msg_low) for r in question_regexes)
    # Если клиент отвечает на вопрос анкеты (хочу снять, арендовать, купить, посуточно) без знака вопроса — это ответ, а не вопрос!
    is_answering_deal = any(w in msg_low for w in ["аренд", "снять", "посут", "куп", "покуп"]) and not has_question_mark
    is_question = (not is_general_inquiry) and (not is_answering_deal) and (has_question_mark or has_word_question)

    prefix = ""

    # Прямой ответ на вопрос о проверенных датах
    if any(q in msg_low for q in ["какие даты", "на какие даты", "какие числа", "какие дни", "проверили даты"]):
        s_date = client_data.get('booking_start_date')
        e_date = client_data.get('booking_end_date')
        if s_date and e_date:
            try:
                from datetime import datetime
                s_dt = datetime.strptime(s_date, "%Y-%m-%d")
                e_dt = datetime.strptime(e_date, "%Y-%m-%d")
                months_ru = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
                nights = (e_dt - s_dt).days
                s_str = f"{s_dt.day} {months_ru[s_dt.month-1]}"
                e_str = f"{e_dt.day} {months_ru[e_dt.month-1]} {e_dt.year} года"
                return f"Подборка проверена на ваши даты: с {s_str} по {e_str} ({nights} ночей)."
            except Exception:
                return f"Подборка проверена на ваши даты: с {s_date} по {e_date}."
        else:
            return "Даты поездки пока не зафиксированы. На какие числа вы планируете поездку?"

    if is_frustrated:
        if "не вилла" in msg_low or "не боаз" in msg_low or "развлечен" in msg_low:
            return "Прошу прощения за неточность в комментарии! Объект Panorama — это действительно комфортные апартаменты 2+1 в Искеле на Лонг Бич, а не вилла в Боазе. Описание исправил. Подскажите, рассматриваем этот вариант или посмотреть другие апартаменты?"
        prefix = "Понял вас, прошу прощения за заминку! Давайте продолжим."
    elif is_general_inquiry and client_data.get('listing_type') == 'sale':
        city = client_data.get('preferred_city') or 'Искеле'
        prefix = f"С удовольствием подберу лучшие варианты для покупки в {city}! У нас актуальная база объектов от проверенных собственников и застройщиков."
    elif is_question:
        # Получаем экспертный ответ от LLM на конкретный вопрос пользователя
        try:
            if telegram_id not in _conversations:
                _conversations[telegram_id] = []
            history = _conversations[telegram_id]
            history.append({"role": "user", "content": user_message})
            if len(history) > 10:
                history = history[-10:]
                _conversations[telegram_id] = history

            # Формируем актуальный контекст профиля клиента для LLM
            profile_ctx = ["Текущий год: 2026."]
            if client_data.get('listing_type'):
                deal = "аренда (посуточная)" if client_data['listing_type'] == 'rent' else "покупка"
                profile_ctx.append(f"- Тип сделки: {deal}")
            if client_data.get('booking_start_date') and client_data.get('booking_end_date'):
                profile_ctx.append(f"- Даты заезда клиента: с {client_data['booking_start_date']} по {client_data['booking_end_date']}")
            if client_data.get('preferred_city'):
                profile_ctx.append(f"- Город/регион: {client_data['preferred_city']}")
            if client_data.get('bedrooms_min'):
                profile_ctx.append(f"- Спален / состав: {client_data['bedrooms_min']} спальни (до 4 человек)")
            if client_data.get('budget_max'):
                profile_ctx.append(f"- Бюджет: до {client_data['budget_max']}€")

            # Добавляем информацию о последнем предложенном объекте, если клиент спрашивает о нем ("это вилла?")
            from bot.handlers import LAST_VIEWED, LAST_SEARCH_RESULTS
            from tools.database import get_property_by_id
            last_p = None
            p_id = LAST_VIEWED.get(telegram_id)
            if not p_id and LAST_SEARCH_RESULTS.get(telegram_id):
                p_id = LAST_SEARCH_RESULTS[telegram_id][0]
            if p_id:
                last_p = await get_property_by_id(p_id)
            if last_p:
                p_type = last_p.get('property_type') or 'не указан'
                p_title = last_p.get('title') or ''
                p_city = last_p.get('city') or ''
                p_dist = last_p.get('district') or ''
                profile_ctx.append(f"- Последний показанный клиенту объект: ID {p_id}, Название: {p_title}, Тип: {p_type}, Локация: {p_dist}, {p_city}")

            ctx_str = "\n".join(profile_ctx)
            dynamic_prompt = f"{LEAD_ANSWER_PROMPT}\n\nКонтекст клиента в системе:\n{ctx_str}\n\nЕсли клиент задает уточняющий вопрос об объекте (например «это вилла?», «где находится?»), отвечай СТРОГО на основе информации о последнем объекте!"

            llm_reply = await ask_llm_with_history(
                system_prompt=dynamic_prompt,
                messages=history,
                temperature=0.3,
                max_tokens=150,
            )
            prefix = llm_reply.strip()
            if "произошла ошибка" in prefix.lower():
                prefix = "Уточняю этот вопрос у старшего риелтора Ильи (@makler_cy). Он свяжется с вами и подробно всё расскажет."
            elif "?" in prefix:
                sentences = re.split(r'(?<=[.!?])\s+', prefix)
                clean_sentences = [s for s in sentences if not s.strip().endswith("?")]
                if clean_sentences:
                    prefix = " ".join(clean_sentences)
            history.append({"role": "assistant", "content": prefix})
        except Exception:
            prefix = ""
    else:
        # Формируем естественное подтверждение на основе того, ЧТО ТОЛЬКО ЧТО ВВЕЛ ПОЛЬЗОВАТЕЛЬ
        msg_low = user_message.lower()
        type_map = {
            'apartment': 'апартаменты', 'квартира': 'апартаменты', 'квартиру': 'апартаменты',
            'villa': 'виллу', 'вилла': 'виллу',
            'penthouse': 'пентхаус', 'пентхаус': 'пентхаус',
            'studio': 'студию', 'студия': 'студию',
            'house': 'дом', 'дом': 'дом',
            'land': 'участок', 'участок': 'участок'
        }
        
        # 1. Даты
        if any(w in msg_low for w in ["сент", "авг", "окт", "ноя", "дек", "янв", "фев", "мар", "апр", "май", "июн", "июл", "дат", "чисел", "числа"]):
            if client_data.get('booking_start_date') and client_data.get('booking_end_date'):
                prefix = f"Даты поездки зафиксировал ({client_data['booking_start_date']} — {client_data['booking_end_date']})."
            else:
                prefix = ""
        # 2. Гости / спальни
        elif any(w in msg_low for w in ["четвер", "трое", "двое", "один", "человек", "гост", "семь", "паро", "пара", "1+1", "2+1", "3+1", "4+1", "студи"]) or (msg_low in ["0", "1", "2", "3", "4", "5"]):
            r_min = client_data.get('bedrooms_min')
            r_max = client_data.get('bedrooms_max')
            if client_data.get('listing_type') == 'rent':
                if r_min == 1 and (r_max is None or r_max == 1):
                    prefix = "Состав гостей записал (1-2 человека, подбираем 1+1/студию)."
                elif r_min == 2 and (r_max is None or r_max == 2):
                    prefix = "Состав гостей записал (семья/компания, подбираем 2+1)."
                elif r_min is not None and r_max is not None and r_min != r_max:
                    prefix = f"Количество комнат зафиксировал ({r_min}+1 и {r_max}+1)."
                else:
                    prefix = "Состав гостей записал."
            else:
                if r_min is not None and r_max is not None and r_min != r_max:
                    if r_min == 0 and r_max == 1:
                        prefix = "Количество спален зафиксировал (студия и 1+1)."
                    else:
                        prefix = f"Количество спален зафиксировал ({r_min}+1 и {r_max}+1)."
                elif r_min == 0:
                    prefix = "Количество спален зафиксировал (студия)."
                elif r_min is not None:
                    prefix = f"Количество спален зафиксировал ({r_min}+1)."
                else:
                    prefix = "Количество спален зафиксировал."
        elif any(w in msg_low for w in ["искеле", "кирени", "фамагуст"]):
            if "искеле" in msg_low:
                city = "Искеле"
            elif "кирени" in msg_low:
                city = "Кирения"
            elif "фамагуст" in msg_low:
                city = "Фамагуста"
            else:
                city = client_data.get('preferred_city') or "Северный Кипр"
            prefix = f"{city} — отличный выбор локации!"
        # 4. Тип недвижимости
        elif any(w in msg_low for w in ["вилл", "villa", "квартир", "апартамент", "пентхаус", "студи", "участок", "land", "дом", "house"]):
            raw_t = client_data.get('preferred_type') or 'apartment'
            parts = [type_map.get(p.strip().lower(), p.strip()) for p in raw_t.split(',')]
            ru_t = ", ".join(parts) if parts else 'апартаменты'
            if client_data.get('listing_type') == 'rent':
                deal = " в аренду"
            elif client_data.get('listing_type') == 'sale':
                deal = " для покупки"
            else:
                deal = ""
            prefix = f"Принято, зафиксировал тип: {ru_t}{deal}."
        # 5. Тип сделки (покупка / аренда)
        elif any(w in msg_low for w in ["куп", "покуп", "приобре", "инвест"]):
            prefix = "Принято, подбираем варианты для покупки."
        elif any(w in msg_low for w in ["аренд", "сним", "посут", "сутк"]):
            prefix = "Принято, подбираем варианты в аренду."
        # 6. Бюджет
        elif any(w in msg_low for w in ["евро", "eur", "€", "долл", "$", "бюджет", "тысяч", "в сутки", "сутки", "тогда"]) or (msg_low.isdigit() and int(msg_low) >= 20):
            b = client_data.get('budget_max')
            if b and b < 999999:
                prefix = f"Ориентир по бюджету зафиксировал (до {b:,.0f}€)."
            else:
                prefix = "Ориентир по бюджету зафиксировал."
        else:
            prefix = "Принято."

    # Если клиент задал вопрос — отвечаем прямо на вопрос, не навязывая следующий шаг анкеты!
    if is_question and prefix:
        await log_interaction(
            client_id=client_data.get('id', 0),
            agent_name="lead_manager",
            action="answer_question",
            details=f"User: {user_message[:100]} | Bot: {prefix[:100]}"
        )
        return prefix

    # Если анкета уже полностью заполнена:
    if not next_q:
        is_refining = any(w in user_message.lower() for w in ["что есть", "какие есть", "покажи", "найди", "подбери", "вариант", "для четвер", "для дво", "другие", "еще", "те же дат"])
        if is_refining or client_data.get('status') != 'qualified':
            if prefix:
                return f"{prefix}\n\n[READY]"
            return "[READY]"
        if prefix:
            return prefix
        return "Все ваши пожелания зафиксированы, старший риелтор Илья (@makler_cy) скоро подключится к диалогу. Если захотите посмотреть другие варианты — просто напишите!"

    # Если еще есть незаполненные шаги анкеты:
    if prefix:
        response = f"{prefix}\n\n{next_q}"
    else:
        response = next_q

    # Логируем
    await log_interaction(
        client_id=client_data.get('id', 0),
        agent_name="lead_manager",
        action="qualify",
        details=f"User: {user_message[:100]} | Bot: {response[:100]}"
    )

    return response
