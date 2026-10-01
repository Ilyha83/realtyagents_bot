# 🏢 AI-Команда Недвижимости (Real Estate Multi-Agent Bot)

[![Telegram Bot](https://img.shields.io/badge/Telegram-@realtyagents__bot-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/realtyagents_bot)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![python-telegram-bot](https://img.shields.io/badge/PTB-v21.6-blue?style=for-the-badge)](https://github.com/python-telegram-bot/python-telegram-bot)
[![LLM Powered](https://img.shields.io/badge/LLM-Llama_3.2_/_OpenAI_API-orange?style=for-the-badge)](https://platform.openai.com/)
[![SQLite WAL](https://img.shields.io/badge/Database-SQLite_WAL-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

Автономная мультиагентная система на базе современных LLM для агентств недвижимости (кейс: **Северный Кипр / ТРСК**).  
Бот полностью автоматизирует воронку продаж: от первого контакта и квалификации лида до интеллектуального подбора объектов из базы, юридических консультаций (налоги, ВНЖ, титулы) и бесшовной передачи горячих клиентов живым менеджерам.

---

## 🌟 Ключевые возможности

1. **Автономная квалификация лидов (Lead Qualification):**
   - Динамический стейт-машин диалога (аренда или покупка, локация, даты проживания, количество спален/гостей, бюджет).
   - Защита от амнезии: бот помнит историю и контекст общения с клиентом.
   - Автоматическая передача «горячего» квалифицированного лида старшим риелторам в Telegram с полной анкетой и ссылкой на прямой диалог.

2. **Интеллектуальный подбор объектов (Smart Property Matcher):**
   - Полнотекстовый и параметрический поиск по каталогу с учетом сотен критериев.
   - Показ объектов в виде галерей с оригинальными медиа-альбомами (фотографиями высокой четкости) и очищенными описаниями без ссылок на сторонние каналы.
   - Интерактивные карточки с кнопками связи с менеджером и бронирования просмотра в 1 клик.

3. **Макро-аналитика рынка (Market Analyst):**
   - Агрегированные ценовые срезы по регионам (Искеле, Кирения, Фамагуста) по категориям студий, 1+1, 2+1, 3+1 и вилл.
   - Анализ доходности от аренды (ROI 6–11.5% годовых).
   - Автоматический расчет рыночных трендов за 1, 2, 3 месяца или за весь период мониторинга.

4. **Юридическая база знаний (Legal & Compliance):**
   - Консультации по налогам (гербовый сбор, НДС, сбор за перевод титула), типам титулов (Эшдегер, Тахсис, Кочан), срокам регистрации контрактов в Кадастре (до 75 дней) и получению ВНЖ.
   - Автоматический юридический дисклеймер к консультациям.

5. **Бесшовная эскалация на человека (Human-in-the-Loop):**
   - Распознавание запроса разговора с живым риелтором или получение номера телефона.
   - Моментальная отправка структурированной заявки администраторам с данными квалификации и объектом интереса.

---

## 🏗 Архитектура мультиагентной системы

Система построена на взаимодействии специализированных агентов:

```mermaid
flowchart TD
    User([👤 Пользователь в Telegram]) <--> Handlers[🤖 Telegram Handlers & UI]
    Handlers <--> Coordinator[🧭 Coordinator Agent\n(Классификация намерений и роутер)]

    Coordinator -->|Квалификация & Чат| LeadManager[💬 Lead Manager Agent\n(Стейт-машина лида + LLM)]
    Coordinator -->|Поиск & Каталог| Matcher[🔍 Property Matcher Agent\n(Параметрический SQL-поиск)]
    Coordinator -->|Цены & Тренды| Analyst[📊 Market Analyst Agent\n(Статистика и аналитика рынка)]
    Coordinator -->|Маркетинг| ContentCreator[✍️ Content Creator Agent\n(Генерация продающих постов)]

    LeadManager <--> DB[(🗄 SQLite WAL DB\nКлиенты & Взаимодействия)]
    Matcher <--> DB
    Analyst <--> AnalyticsDB[(📈 Analytics DB\nМониторинг предложений)]

    LeadManager -.->|Горячий лид / Заявка| ManagerAlert[🛎 Уведомление риелторам в Telegram]
    Handlers -.->|Заявка на просмотр| ManagerAlert
```

### Специализация агентов:
* **`Coordinator Agent`** (`agents/coordinator.py`) — маршрутизирует запросы пользователя, производит первичное детерминированное извлечение дат, бюджета, типов недвижимости и спален с валидацией.
* **`Lead Manager Agent`** (`agents/lead_manager.py`) — ведет диалог, мягко доквалифицирует параметры клиента, сохраняет CRM-состояние и генерирует персональные ответы через LLM.
* **`Property Matcher Agent`** (`agents/property_matcher.py`) — преобразует пожелания клиента в SQL-запросы, ранжирует результаты и генерирует структурированную выдачу.
* **`Market Analyst Agent`** (`agents/market_analyst.py`) — рассчитывает средние, минимальные и максимальные цены на основе тысяч объявлений, оценивает доходность и формирует аналитические отчеты.
* **`Content Creator Agent`** (`agents/content_creator.py`) — формирует рекламные посты для соцсетей по объектам из базы.

---

## 🛠 Технологический стек

* **Язык разработки:** Python 3.10+
* **Telegram Framework:** `python-telegram-bot` v21.6 (полностью асинхронный `asyncio`)
* **LLM & AI:** OpenAI API / NVIDIA NIM API (`meta/llama-3.2-11b-vision-instruct`, `meta/llama-3.1-70b-instruct`)
* **База данных:** SQLite 3 с включенным режимом **WAL (Write-Ahead Logging)** и `aiosqlite` для высокой конкурентности без блокировок.
* **Парсинг и обработка данных:** `BeautifulSoup4`, `httpx`, `re` (регулярные выражения для парсинга дат и диапазонов цен).
* **Инфраструктура & DevOps:** Ubuntu 22.04 LTS, `systemd` daemon c политикой авто-перезапуска, встроенный `Pre-flight Harness` самодиагностики при старте.

---

## ⚙️ Надежность и Production-решения

* **Изоляция дат и спален:** кастомный парсер исключает ложные срабатывания (например, диапазон дат *«23-30 сентября»* никогда не интерпретируется как спальни).
* **Отказоустойчивость Telegram API:** реализована обертка `safe_reply` — при возникновении ошибок парсинга сущностей Markdown (например, спецсимволы в именах пользователей) сообщение автоматически отправляется в чистом виде, гарантируя непрерывность диалога.
* **Встроенный Pre-flight стенд:** перед началом приема сообщений бот проверяет целостность БД, статус WAL и пинг LLM API.
* **Комплексные тесты:** регрессионный тест-сьют покрывает все пользовательские сценарии (`tests/test_full_flows.py`, `tests/test_stability.py`).

---

## 🚀 Быстрый старт

### 1. Клонирование репозитория
```bash
git clone https://github.com/Ilyha83/realtyagents_bot.git
cd realtyagents_bot
```

### 2. Установка зависимостей
```bash
python -m venv venv
# Linux / macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Настройка переменных окружения
Скопируйте файл `.env.example` в `.env` и укажите ваши ключи:
```bash
cp .env.example .env
```
Заполните параметры:
```env
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
NVIDIA_API_KEY=ваш_ключ_api
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=meta/llama-3.2-11b-vision-instruct
MANAGER_CHAT_IDS=telegram_id_менеджера1,telegram_id_менеджера2
```

### 4. Первичная инициализация базы данных
```bash
python seed.py
```

### 5. Запуск тестов
```bash
python tests/test_full_flows.py
python tests/test_stability.py
```

### 6. Запуск бота
```bash
python main.py
```

---

## 📂 Структура проекта

```text
├── agents/                  # Логика AI-агентов
│   ├── coordinator.py       # Координатор и классификатор намерений
│   ├── lead_manager.py      # Лид-менеджер и квалификационная воронка
│   ├── property_matcher.py  # Агент подбора объектов
│   ├── market_analyst.py    # Аналитик рынка и юридическая база
│   └── content_creator.py   # Контент-мейкер
├── bot/                     # Интерфейс Telegram
│   ├── handlers.py          # Обработчики сообщений и callback-кнопок
│   └── keyboards.py         # Инлайн-клавиатуры
├── tools/                   # Инструменты и утилиты
│   ├── database.py          # Работа с SQLite (async / sync)
│   ├── llm.py               # Клиент LLM с retry-логикой
│   ├── dates.py             # Парсер дат
│   └── parser_101evler.py   # Парсер каталога
├── tests/                   # Набор автоматических тестов
│   ├── test_full_flows.py   # Комплексные регрессионные тесты сценариев
│   └── test_stability.py    # Стресс-тест WAL и параллельных запросов
├── data/                    # Базы знаний и кэши
│   ├── legal_kb.json        # Юридическая база знаний
│   └── content_examples.json# Примеры маркетинговых постов
├── main.py                  # Главная точка входа бота
├── seed.py                  # Скрипт наполнения тестовыми данными
├── requirements.txt         # Зависимости проекта
└── .env.example             # Пример конфигурации
```

---

## 👨‍💻 Автор и контакты

* **Разработчик:** Илья Тарасов ([@makler_cy](https://t.me/makler_cy))
* **Email:** egorjan.t112@gmail.com
* **Live Demo:** [@realtyagents_bot](https://t.me/realtyagents_bot)
