from typing import Dict, Optional, Any
import io

from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import mm


def build_pdf_report(
    candidate: Dict[str, Any],
    test_type: Optional[str],
    scores: Dict[str, float],
    report: Optional[Dict[str, Any]],
    voice: Optional[Dict[str, Any]],
    photo: Optional[Dict[str, Any]],
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.alignment = TA_LEFT

    title_style = styles["Heading1"]
    title_style.textColor = colors.HexColor("#1f2933")
    title_style.fontSize = 18

    h2 = styles["Heading2"]
    h2.textColor = colors.HexColor("#334e68")
    h2.fontSize = 14

    body = []

    body.append(Paragraph("AI HR Psychologist · Звіт по кандидату", title_style))
    body.append(Spacer(1, 8))

    full_name = candidate.get("full_name") or "Без імені"
    meta = f"ID: {candidate.get('id')} · TG ID: {candidate.get('tg_id')} · Створено: {candidate.get('created_at')}"
    body.append(Paragraph(f"<b>Кандидат:</b> {full_name}", normal))
    body.append(Paragraph(meta, normal))
    body.append(Spacer(1, 10))

    if test_type:
        body.append(Paragraph(f"Останній тест: {test_type}", normal))
    else:
        body.append(Paragraph("Останній тест: немає даних", normal))
    body.append(Spacer(1, 4))

    body.append(Paragraph("Профіль за шкалами", h2))
    if scores:
        for k, v in scores.items():
            body.append(Paragraph(f"{k}: {v:.2f} / 5", normal))
    else:
        body.append(Paragraph("Немає результатів тесту.", normal))
    body.append(Spacer(1, 10))

    body.append(Paragraph("AI-опис та рекомендації", h2))
    if report:
        body.append(Paragraph(f"<b>Короткий опис:</b> {report.get('summary','')}", normal))
        body.append(Paragraph(f"<b>Ризик-профіль:</b> {report.get('risk_level','невідомо')}", normal))
        body.append(Spacer(1, 4))
        recs = report.get("recommendations") or []
        if recs:
            body.append(Paragraph("<b>Рекомендації:</b>", normal))
            for r in recs:
                body.append(Paragraph("• " + r, normal))
        else:
            body.append(Paragraph("Немає рекомендацій.", normal))
    else:
        body.append(Paragraph("Немає збереженого звіту.", normal))
    body.append(Spacer(1, 10))

    body.append(Paragraph("Аналіз голосу (стрес / напруга)", h2))
    if voice:
        body.append(Paragraph(f"Оцінка стресу: {voice.get('stress_score',0):.2f} / 100", normal))
        body.append(Paragraph(f"Рівень: {voice.get('level','невідомо')}", normal))
        body.append(Paragraph(f"Дата: {voice.get('created_at','')}", normal))
    else:
        body.append(Paragraph("Немає записів голосового аналізу.", normal))
    body.append(Spacer(1, 10))

    body.append(Paragraph("Аналіз фото (емоції / втома)", h2))
    if photo:
        body.append(Paragraph(f"Настрій: {photo.get('mood','')}", normal))
        body.append(Paragraph(f"Рівень втоми: {photo.get('fatigue_level','')}", normal))
        body.append(
            Paragraph(
                f"Яскравість: {photo.get('brightness',0):.1f} · Контраст: {photo.get('contrast',0):.1f}",
                normal,
            )
        )
        body.append(Paragraph(f"Дата: {photo.get('created_at','')}", normal))
    else:
        body.append(Paragraph("Немає останнього фотоаналізу.", normal))

    doc.build(body)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf