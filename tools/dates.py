# -*- coding: utf-8 -*-
import re

def extract_booking_dates(text: str, current_year: int = 2026) -> tuple:
    t = text.lower().strip()
    t = re.sub(r'[\.\,\!\?]+$', '', t)
    months_map = {
        'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'май': 5, 'мая': 5,
        'июн': 6, 'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12
    }
    m1 = re.search(r'(?:с\s*)?(\d{1,2})\s*(?:[-–—]|по)\s*(\d{1,2})\s+([а-яёА-ЯЁ]+)', t)
    if m1:
        d1, d2, mon_str = int(m1.group(1)), int(m1.group(2)), m1.group(3).lower()
        for prefix, m_num in months_map.items():
            if mon_str.startswith(prefix):
                return (f'{current_year:04d}-{m_num:02d}-{d1:02d}', f'{current_year:04d}-{m_num:02d}-{d2:02d}')
    m2 = re.search(r'(\d{1,2})\.(\d{1,2})\s*[-–—]\s*(\d{1,2})\.(\d{1,2})', t)
    if m2:
        d1, m1_num, d2, m2_num = int(m2.group(1)), int(m2.group(2)), int(m2.group(3)), int(m2.group(4))
        return (f'{current_year:04d}-{m1_num:02d}-{d1:02d}', f'{current_year:04d}-{m2_num:02d}-{d2:02d}')
    m3 = re.search(r'(\d{1,2})\s*[-–—]\s*(\d{1,2})\.([01]?\d)', t)
    if m3:
        d1, d2, m_num = int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
        return (f'{current_year:04d}-{m_num:02d}-{d1:02d}', f'{current_year:04d}-{m_num:02d}-{d2:02d}')
    m4 = re.search(r'(\d{1,2})\s+([а-яёА-ЯЁ]+)\s*[-–—]\s*(\d{1,2})\s+([а-яёА-ЯЁ]+)', t)
    if m4:
        d1, mon1_str, d2, mon2_str = int(m4.group(1)), m4.group(2).lower(), int(m4.group(3)), m4.group(4).lower()
        m1_num = next((v for k, v in months_map.items() if mon1_str.startswith(k)), None)
        m2_num = next((v for k, v in months_map.items() if mon2_str.startswith(k)), None)
        if m1_num and m2_num:
            return (f'{current_year:04d}-{m1_num:02d}-{d1:02d}', f'{current_year:04d}-{m2_num:02d}-{d2:02d}')
    return None, None
