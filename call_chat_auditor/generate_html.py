# -*- coding: utf-8 -*-
"""
generate_html.py — Генератор веб-отчётов (HTML) для AI-Sales Auditor.
"""

import os
import json


def create_auditor_html(report: dict, output_filename: str = "report_sales_audit.html"):
    """Создаёт стильную HTML-страницу отчёта аудита продаж."""
    manager = report.get("manager_name", "Менеджер")
    comm_type = report.get("communication_type", "коммуникация")
    score = report.get("overall_score_percent", 0)
    summary = report.get("summary", "")

    # Определение цвета KPI
    score_color = "#10B981" if score >= 80 else ("#F59E0B" if score >= 60 else "#EF4444")
    status_text = "Отлично" if score >= 80 else ("Требует внимания" if score >= 60 else "Критический уровень")

    criteria = report.get("criteria_scores", {})
    labels = {
        "greeting": "Приветствие и контакт",
        "initiative": "Инициатива и ведение диалога",
        "needs_discovery": "Выявление потребностей",
        "presentation": "Презентация решения",
        "objections_handling": "Отработка возражений",
        "compliance": "Соблюдение регламента и скорость",
        "closing_next_step": "Закрытие на следующий шаг"
    }

    criteria_html = ""
    for key, label in labels.items():
        c_data = criteria.get(key, {})
        c_score = c_data.get("score", 0)
        c_comment = c_data.get("comment", "")
        bar_w = c_score * 10
        bar_color = "#10B981" if c_score >= 8 else ("#F59E0B" if c_score >= 5 else "#EF4444")

        criteria_html += f"""
        <div style="margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 14px;">
                <span style="font-weight: 600; color: #374151;">{label}</span>
                <span style="font-weight: 700; color: {bar_color};">{c_score}/10</span>
            </div>
            <div style="background: #E5E7EB; height: 10px; border-radius: 5px; overflow: hidden; margin-bottom: 6px;">
                <div style="background: {bar_color}; width: {bar_w}%; height: 100%; border-radius: 5px; transition: width 1s;"></div>
            </div>
            <div style="font-size: 13px; color: #6B7280; font-style: italic;">{c_comment}</div>
        </div>
        """

    violations = report.get("critical_violations", [])
    violations_html = ""
    if violations:
        items = "".join([f"<li style='margin-bottom: 6px;'>{v}</li>" for v in violations])
        violations_html = f"""
        <div style="background: #FEF2F2; border-left: 4px solid #EF4444; padding: 16px; border-radius: 8px; margin-bottom: 24px;">
            <h3 style="margin: 0 0 10px 0; color: #991B1B; font-size: 16px;">⚠️ Критические ошибки и нарушения</h3>
            <ul style="margin: 0; padding-left: 20px; color: #7F1D1D; font-size: 14px;">{items}</ul>
        </div>
        """

    recommendations = report.get("recommendations", [])
    recs_html = ""
    if recommendations:
        items = "".join([f"<li style='margin-bottom: 6px;'>{r}</li>" for r in recommendations])
        recs_html = f"""
        <div style="background: #ECFDF5; border-left: 4px solid #10B981; padding: 16px; border-radius: 8px;">
            <h3 style="margin: 0 0 10px 0; color: #065F46; font-size: 16px;">💡 Рекомендации для роста продаж</h3>
            <ul style="margin: 0; padding-left: 20px; color: #047857; font-size: 14px;">{items}</ul>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>AI Sales Audit — {manager}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background: #F3F4F6; color: #1F2937; margin: 0; padding: 30px; }}
        .container {{ max-width: 850px; margin: 0 auto; background: #FFFFFF; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: #1E293B; color: #FFFFFF; padding: 30px; display: flex; justify-content: space-between; align-items: center; }}
        .header h1 {{ margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
        .header p {{ margin: 5px 0 0 0; color: #94A3B8; font-size: 14px; }}
        .kpi-badge {{ background: {score_color}; color: #FFFFFF; padding: 12px 24px; border-radius: 12px; text-align: center; font-weight: 800; }}
        .kpi-score {{ font-size: 28px; line-height: 1; }}
        .kpi-label {{ font-size: 11px; text-transform: uppercase; margin-top: 4px; opacity: 0.9; }}
        .content {{ padding: 30px; }}
        .summary-box {{ background: #F8FAFC; border: 1px solid #E2E8F0; padding: 20px; border-radius: 12px; margin-bottom: 24px; font-size: 15px; line-height: 1.6; color: #334155; }}
        .section-title {{ font-size: 18px; font-weight: 700; margin-bottom: 16px; color: #0F172A; border-bottom: 2px solid #F1F5F9; padding-bottom: 8px; }}
        .footer {{ background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 20px; text-align: center; font-size: 13px; color: #64748B; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>📊 AI-Аудит продаж: {manager}</h1>
                <p>Тип коммуникации: {comm_type.capitalize()} | Статус: {status_text}</p>
            </div>
            <div class="kpi-badge">
                <div class="kpi-score">{score}%</div>
                <div class="kpi-label">Индекс KPI</div>
            </div>
        </div>

        <div class="content">
            <div class="summary-box">
                <strong>📝 Главное резюме аудита:</strong><br>
                {summary}
            </div>

            {violations_html}

            <div class="section-title">🎯 Оценки по критериям качества</div>
            {criteria_html}

            <br>
            {recs_html}
        </div>

        <div class="footer">
            Сгенерировано AI-Sales Auditor | Система управления качеством коммуникаций
        </div>
    </div>
</body>
</html>
"""
    output_path = os.path.join(os.path.dirname(__file__), output_filename)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"🌐 Создан HTML-отчёт: {output_path}")
