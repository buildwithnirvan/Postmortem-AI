"""Generates high quality, formatted downloadable PDF postmortem documents using ReportLab."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import IncidentInput, Plan


def generate_pdf_report(
    incident_id: str,
    incident: IncidentInput,
    plan: Plan,
    outcomes: list[dict[str, Any]],
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
    )
    h2_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0369a1"),
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#334155"),
    )
    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748b"),
    )

    story = []

    # Title & Badge
    story.append(Paragraph(f"POSTMORTEM REPORT: {incident_id}", title_style))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            f"<b>Service:</b> {incident.service} &nbsp;|&nbsp; "
            f"<b>Severity:</b> {incident.severity.upper()} &nbsp;|&nbsp; "
            f"<b>Environment:</b> {incident.environment.upper()} &nbsp;|&nbsp; "
            f"<b>Category:</b> {plan.incident_category.upper()}",
            meta_style,
        )
    )
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=14))

    # Executive Summary
    story.append(Paragraph("1. Executive Summary", h2_style))
    story.append(Paragraph(plan.summary, body_style))
    if plan.initial_impact:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Business Impact:</b> {plan.initial_impact}", body_style))

    # RCA
    rca = plan.rca
    if rca:
        story.append(Spacer(1, 10))
        story.append(Paragraph("2. Root Cause Analysis (RCA)", h2_style))
        story.append(
            Paragraph(
                f"<b>Primary Hypothesis ({rca.confidence.upper()} CONFIDENCE):</b><br/>"
                f"{rca.primary_hypothesis}",
                body_style,
            )
        )
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Analysis Details:</b> {rca.confidence_explanation}", body_style))

        if rca.contributing_factors:
            story.append(Spacer(1, 4))
            factors_str = "<br/>• ".join(rca.contributing_factors)
            story.append(Paragraph(f"<b>Contributing Factors:</b><br/>• {factors_str}", body_style))

    # Actions Taken & Outcomes Table
    story.append(Spacer(1, 12))
    story.append(Paragraph("3. Troubleshooting Actions & Confirmed Outcomes", h2_style))

    table_data = [["#", "Action & Rationale", "Risk", "Outcome", "Engineer Notes"]]
    for a in plan.actions:
        res = "NOT TRIED"
        notes = ""
        for o in outcomes:
            if o.get("action_id") == a.id:
                res = o.get("result", "not_tried").upper()
                notes = o.get("notes", "")
                break

        action_cell = Paragraph(f"<b>{a.title}</b><br/>{a.rationale}", body_style)
        notes_cell = Paragraph(notes or "—", meta_style)

        table_data.append([
            str(a.priority),
            action_cell,
            a.risk.upper(),
            res,
            notes_cell,
        ])

    table = Table(table_data, colWidths=[24, 250, 48, 65, 145])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ])
    )
    story.append(table)

    # Permanent Resolution & Prevention
    if rca and (rca.recommended_permanent_fix or rca.preventive_actions):
        story.append(Spacer(1, 12))
        story.append(Paragraph("4. Permanent Fix & Preventive Guardrails", h2_style))
        if rca.recommended_permanent_fix:
            story.append(
                Paragraph(f"<b>Permanent Fix:</b> {rca.recommended_permanent_fix}", body_style)
            )
        if rca.preventive_actions:
            story.append(Spacer(1, 4))
            prev_str = "<br/>• ".join(rca.preventive_actions)
            story.append(Paragraph(f"<b>Preventive Actions:</b><br/>• {prev_str}", body_style))

    # Lessons in Hindsight
    if plan.memories:
        story.append(Spacer(1, 12))
        story.append(Paragraph("5. Lessons Retained in Hindsight Memory", h2_style))
        for m in plan.memories:
            story.append(
                Paragraph(
                    f"• <b>[{m.ref}]</b> {m.text} <i>(Outcome: {m.outcome or 'cited'})</i>",
                    body_style,
                )
            )
            story.append(Spacer(1, 2))

    doc.build(story)
    return buffer.getvalue()

