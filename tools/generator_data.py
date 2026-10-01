# -*- coding: utf-8 -*-
"""
generator_data.py — Скрипт генерации реалистичной базы данных недвижимости Северного Кипра.
"""

import asyncio
import os
import sys
import random
import json
import sqlite3

# Fix encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'properties.db')

CITIES_DISTRICTS = {
    "Кирения": ["Чаталкёй", "Алсанджак", "Лапта", "Беллапаис", "Караоланолу", "Центр Кирении"],
    "Искеле": ["Long Beach", "Бафра", "Боаз", "Центр Искеле"],
    "Фамагуста": ["Енибоазичи", "Центр Фамагусты", "Калаичи"],
    "Никосия": ["Гёчюменкёй", "Ортакёй", "Центр Никосии"],
    "Гюзельюрт": ["Центр Гюзельюрта"],
    "Лефке": ["Газиверен", "Центр Лефке"]
}

TYPES = ["квартира", "вилла", "пентхаус", "студия", "участок"]

FEATURES_POOL = [
    "Вид на море", "Личный бассейн", "Общий бассейн", "Рассрочка", "Первая линия",
    "Меблирована", "Кондиционеры", "Паркинг", "Сад", "Камин", "Рядом с пляжем",
    "Рядом с университетом", "С бытовой техникой", "Джакузи", "Охрана 24/7",
    "Тёплый пол", "Панорамные окна"
]

TITLES_TEMPLATES = {
    "квартира": [
        "Современная квартира {bedrooms}+{bathrooms} в жилом комплексе с бассейном",
        "Апартаменты {bedrooms}+{bathrooms} с видом на море",
        "Уютная квартира {bedrooms}+{bathrooms} рядом со всей инфраструктурой",
        "Инвестиционная квартира {bedrooms}+{bathrooms} под сдачу в аренду",
        "Просторная квартира {bedrooms}+{bathrooms} в тихом районе"
    ],
    "вилла": [
        "Роскошная вилла {bedrooms}+{bathrooms} с частным бассейном и садом",
        "Элитная вилла {bedrooms}+{bathrooms} на первой линии у моря",
        "Современная вилла {bedrooms}+{bathrooms} с панорамным видом на горы и море",
        "Уютный семейный дом {bedrooms}+{bathrooms} с камином и приватной территорией",
        "Вилла класса люкс {bedrooms}+{bathrooms} с беспроцентной рассрочкой"
    ],
    "пентхаус": [
        "Эксклюзивный пентхаус {bedrooms}+{bathrooms} с огромной террасой на крыше",
        "Роскошный пентхаус {bedrooms}+{bathrooms} с джакузи и панорамным видом",
        "Двухуровневый пентхаус {bedrooms}+{bathrooms} в элитном комплексе",
        "Пентхаус {bedrooms}+{bathrooms} на первой береговой линии"
    ],
    "студия": [
        "Студия 0+1 с балконом в современном курортном комплексе",
        "Уютная студия 0+1 с видом на бассейн в шаговой доступности от пляжа",
        "Инвестиционная студия 0+1 с гарантированным доходом от аренды",
        "Студия 0+1 рядом с университетом EMU"
    ],
    "участок": [
        "Земельный участок под строительство виллы с видом на море",
        "Инвестиционный земельный участок под застройку",
        "Участок земли с готовым разрешением на строительство и титулом"
    ]
}

DESCRIPTIONS = [
    "Превосходное расположение, идеально подходящее как для постоянного проживания, так и для отдыха или сдачи в аренду.",
    "В пешей доступности находятся супермаркеты, рестораны, песчаные пляжи и школы. Очень тихий и престижный район.",
    "Комплекс предлагает развитую инфраструктуру: спа-центр, фитнес-клуб, детские площадки и зоны барбекю.",
    "Объект сдается с высококачественной чистовой отделкой, встроенной кухней и полностью оборудованными санузлами.",
    "Доступна очень гибкая беспроцентная рассрочка платежа до завершения строительства и получения ключей.",
    "Панорамное остекление наполняет пространство естественным светом. С террасы открывается фантастический вид."
]

def generate_property(prop_id):
    city = random.choice(list(CITIES_DISTRICTS.keys()))
    district = random.choice(CITIES_DISTRICTS[city])
    prop_type = random.choice(TYPES)
    
    # Специфика комнат
    if prop_type == "студия":
        bedrooms = 0
        bathrooms = 1
        area_m2 = random.randint(35, 55)
        price = random.randint(55000, 95000)
    elif prop_type == "участок":
        bedrooms = 0
        bathrooms = 0
        area_m2 = random.randint(400, 2000)
        price = random.randint(80000, 350000)
    elif prop_type == "вилла":
        bedrooms = random.randint(3, 5)
        bathrooms = random.randint(2, bedrooms)
        area_m2 = random.randint(150, 450)
        price = random.randint(190000, 1200000)
    elif prop_type == "пентхаус":
        bedrooms = random.randint(2, 4)
        bathrooms = random.randint(2, bedrooms)
        area_m2 = random.randint(100, 250)
        price = random.randint(160000, 600000)
    else: # квартира
        bedrooms = random.randint(1, 3)
        bathrooms = random.randint(1, min(2, bedrooms))
        area_m2 = random.randint(50, 120)
        price = random.randint(85000, 250000)

    # Некоторые корректировки цен по регионам
    if city == "Кирения":
        price = int(price * 1.25) # Кирения дороже
    elif city == "Никосия":
        price = int(price * 0.95)
    elif city == "Искеле" and district == "Long Beach":
        price = int(price * 1.15)
        
    title_tpl = random.choice(TITLES_TEMPLATES[prop_type])
    title = title_tpl.format(bedrooms=bedrooms, bathrooms=bathrooms)
    title += f" в {district} ({city})"

    # Собираем фичи
    features = []
    if prop_type in ["вилла", "пентхаус"]:
        features.append("Вид на море")
        if random.random() > 0.4:
            features.append("Личный бассейн" if prop_type == "вилла" else "Джакузи")
    elif random.random() > 0.5:
        features.append("Общий бассейн")
    
    if random.random() > 0.3:
        features.append("Рассрочка")
    if random.random() > 0.7:
        features.append("Первая линия")
    if random.random() > 0.4:
        features.append("Меблирована")
    if random.random() > 0.3:
        features.append("Паркинг")
    if city == "Фамагуста" and random.random() > 0.4:
        features.append("Рядом с университетом")
    
    # Добавляем случайные из пула
    for f in random.sample(FEATURES_POOL, random.randint(1, 3)):
        if f not in features:
            features.append(f)

    # Описание
    desc_sentences = random.sample(DESCRIPTIONS, random.randint(2, 4))
    description = f"{title}. " + " ".join(desc_sentences)
    if "Рассрочка" in features:
        description += " Доступна рассрочка от застройщика с первоначальным взносом всего от 30%."
    if "Вид на море" in features:
        description += " Панорамный вид на Средиземное море прямо из ваших окон."

    # Фото
    photo_urls = [
        "https://images.unsplash.com/photo-1613977257363-707ba9348227?w=800",
        "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?w=800",
        "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800",
        "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800"
    ]
    photos = [random.choice(photo_urls)]

    return {
        "source": "generator",
        "source_url": f"https://101evler.com/sale/residence/generated-{prop_id}",
        "title": title,
        "property_type": prop_type,
        "listing_type": "sale",
        "city": city,
        "district": district,
        "price": float(price),
        "currency": "GBP",
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "area_m2": float(area_m2),
        "floor": random.randint(1, 4) if prop_type not in ["вилла", "участок"] else None,
        "total_floors": random.randint(4, 10) if prop_type not in ["вилла", "участок"] else None,
        "year_built": random.randint(2021, 2026),
        "description": description,
        "features": features,
        "photos": photos,
        "contact_name": "Digital Agent Ltd",
        "contact_phone": "+90 533 888 88 88"
    }

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Сначала очистим старые тестовые данные
    cursor.execute("DELETE FROM properties WHERE source = 'generator' OR source = '101evler_demo'")
    conn.commit()
    
    print(f"Generating properties...")
    count = 1000
    for i in range(1, count + 1):
        p = generate_property(i)
        cursor.execute('''
            INSERT INTO properties (
                source, source_url, title, property_type, listing_type,
                city, district, price, currency, bedrooms, bathrooms,
                area_m2, floor, total_floors, year_built, description,
                features, photos, contact_name, contact_phone, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ''', (
            p['source'],
            p['source_url'],
            p['title'],
            p['property_type'],
            p['listing_type'],
            p['city'],
            p['district'],
            p['price'],
            p['currency'],
            p['bedrooms'],
            p['bathrooms'],
            p['area_m2'],
            p['floor'],
            p['total_floors'],
            p['year_built'],
            p['description'],
            json.dumps(p['features'], ensure_ascii=False),
            json.dumps(p['photos'], ensure_ascii=False),
            p['contact_name'],
            p['contact_phone']
        ))
        
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM properties WHERE is_active = 1")
    total = cursor.fetchone()[0]
    conn.close()
    print(f"Successfully generated and inserted {count} realistic properties. Total properties in DB: {total}")

if __name__ == "__main__":
    main()
