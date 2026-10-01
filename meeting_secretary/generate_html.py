# -*- coding: utf-8 -*-
"""
generate_html.py — Генератор веб-протоколов (HTML) для AI-Meeting Secretary.
"""

import os
import json


def create_meeting_html(data: dict, output_filename: str = "report_meeting_protocol.html"):
    """Создаёт стильный HTML-протокол совещания."""
    title = data.get("meeting_title", "Планёрка")
    summary = data.get("summary", "")
    score = data.get("efficiency_score", 0)

    decisions = data.get("key_decisions", [])
    decisions_html = "".join([f"<li style='margin-bottom: 8px; font-weight: 500;'>{d}</li>" for d in decisions])

    actions = data.get("action_items", [])
    actions_rows = ""
    for a in actions:
        who = a.get("assignee", "Не указан")
        task = a.get("task", "")
        dl = a.get("deadline", "Без срока")
        actions_rows += f"""
        <tr style="border-bottom: 1px solid #E2E8F0;">
            <td style="padding: 12px; font-weight: 600; color: #1E293B;">👤 {who}</td>
            <td style="padding: 12px; color: #334155;">{task}</td>
            <td style="padding: 12px; color: #DC2626; font-weight: 600; white-space: nowrap;">⏰ {dl}</td>
        </tr>
        """

    stuck = data.get("stuck_topics", [])
    stuck_html = ""
    if stuck:
        items = "".join([f"<li style='margin-bottom: 6px;'>{s}</li>" for s in stuck])
        stuck_html = f"""
        <div style="background: #FFFBEB; border-left: 4px solid #F59E0B; padding: 16px; border-radius: 8px; margin-bottom: 24px;">
            <h3 style="margin: 0 0 10px 0; color: #B45309; font-size: 16px;">⏳ Зависшие / Отложенные вопросы</h3>
            <ul style="margin: 0; padding-left: 20px; color: #92400E; font-size: 14px;">{items}</ul>
        </div>
        """

    kpi = data.get("participants_kpi", [])
    kpi_html = ""
    for p in kpi:
        name = p.get("name", "")
        role_sum = p.get("role_summary", "")
        kpi_html += f"""
        <div style="background: #F8FAFC; padding: 12px 16px; border-radius: 8px; margin-bottom: 8px; border: 1px solid #E2E8F0;">
            <strong style="color: #0F172A;">{name}:</strong> <span style="color: #475569; font-size: 14px;">{role_sum}</span>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Протокол — {title}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background: #F1F5F9; color: #1E293B; margin: 0; padding: 30px; }}
        .container {{ max-width: 900px; margin: 0 auto; background: #FFFFFF; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.06); overflow: hidden; }}
        .header {{ background: #0F172A; color: #FFFFFF; padding: 30px; display: flex; justify-content: space-between; align-items: center; }}
        .header h1 {{ margin: 0; font-size: 24px; font-weight: 800; }}
        .header p {{ margin: 5px 0 0 0; color: #94A3B8; font-size: 14px; }}
        .score-badge {{ background: #3B82F6; color: #FFFFFF; padding: 10px 20px; border-radius: 10px; text-align: center; font-weight: 700; font-size: 20px; }}
        .content {{ padding: 30px; }}
        .summary {{ background: #EFF6FF; border-left: 4px solid #3B82F6; padding: 16px; border-radius: 8px; margin-bottom: 24px; color: #1E40AF; font-size: 15px; line-height: 1.6; }}
        .section-title {{ font-size: 18px; font-weight: 700; margin: 24px 0 14px 0; color: #0F172A; border-bottom: 2px solid #E2E8F0; padding-bottom: 6px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; background: #FFFFFF; border-radius: 8px; overflow: hidden; border: 1px solid #E2E8F0; }}
        th {{ background: #F8FAFC; text-align: left; padding: 12px; font-size: 13px; text-transform: uppercase; color: #64748B; border-bottom: 2px solid #E2E8F0; }}
        .footer {{ background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 20px; text-align: center; font-size: 13px; color: #64748B; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>📋 {title}</h1>
                <p>Официальный AI-протокол совещания руководства</p>
            </div>
            <div class="score-badge">
                Эффективность: {score}%
            </div>
        </div>

        <div class="content">
            <div class="summary">
                <strong>📖 Главное резюме встречи:</strong><br>
                {summary}
            </div>

            <div class="section-title">✅ Принятые решения</div>
            <ol style="padding-left: 20px; color: #334155; font-size: 15px; line-height: 1.6;">
                {decisions_html}
            </ol>

            <div class="section-title">🎯 Поручения и задачи (Action Items)</div>
            <table>
                <thead>
                    <tr>
                        <th style="width: 25%;">Ответственный</th>
                        <th>Поручение / Задача</th>
                        <th style="width: 20%;">Срок</th>
                    </tr>
                </thead>
                <tbody>
                    {actions_rows}
                </tbody>
            </table>

            {stuck_html}

            <div class="section-title">👥 Вклад участников встречи</div>
            {kpi_html}
        </div>

        <div class="footer">
            Сгенерировано AI-Meeting Secretary | Система автоматизации управления
        </div>
    </div>
</body>
</html>
"""
    output_path = os.path.join(os.path.dirname(__file__), output_filename)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"🌐 Создан HTML-протокол: {output_path}")
