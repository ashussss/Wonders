"""ICS calendar invite + PDF one-pager generators."""
from __future__ import annotations
import io
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from ics import Calendar, Event
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.enums import TA_LEFT


def build_ics(webinar: Dict[str, Any]) -> bytes:
    c = Calendar()
    e = Event()
    e.name = webinar.get("title", "Webinar")
    e.description = (webinar.get("description") or "") + (
        f"\n\nJoin link: {webinar['join_link']}" if webinar.get("join_link") else ""
    )
    start_iso = webinar["starts_at"].replace("Z", "+00:00")
    start = datetime.fromisoformat(start_iso)
    e.begin = start
    e.end = start + timedelta(hours=1)
    if webinar.get("join_link"):
        e.url = webinar["join_link"]
    e.uid = f"showup-{webinar['id']}@showup.ai"
    c.events.add(e)
    return str(c).encode("utf-8")


def build_one_pager_pdf(webinar: Dict[str, Any], one_pager: Dict[str, Any]) -> bytes:
    """Render a simple one-pager PDF from the lead-magnet outline."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title=one_pager.get("title", webinar.get("title", "One-pager")))
    styles = getSampleStyleSheet()
    orange = HexColor("#EA580C")
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=orange, fontSize=22,
                        leading=26, spaceAfter=18, alignment=TA_LEFT)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14, leading=18,
                        textColor=HexColor("#111827"), spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10.5, leading=15,
                          textColor=HexColor("#374151"))
    muted = ParagraphStyle("muted", parent=body, textColor=HexColor("#9CA3AF"), fontSize=8.5)

    flow = []
    flow.append(Paragraph("ShowUp.ai · Companion Guide", muted))
    flow.append(Paragraph(one_pager.get("title") or webinar.get("title", "Guide"), h1))
    flow.append(Paragraph(f"<b>Webinar:</b> {webinar.get('title','')}", body))
    if webinar.get("speaker"):
        flow.append(Paragraph(f"<b>Speaker:</b> {webinar['speaker']}", body))
    flow.append(Spacer(1, 12))
    if webinar.get("description"):
        flow.append(Paragraph(webinar["description"], body))
        flow.append(Spacer(1, 10))
    flow.append(Paragraph("What you'll learn", h2))
    items: List = []
    for section in (one_pager.get("outline") or [])[:20]:
        items.append(ListItem(Paragraph(section, body), leftIndent=6))
    if items:
        flow.append(ListFlowable(items, bulletType="bullet", bulletColor=orange, leftIndent=14, bulletFontSize=10))
    flow.append(Spacer(1, 18))
    flow.append(Paragraph("Verify before sharing — illustrative content", muted))
    flow.append(Paragraph(
        "This guide was AI-drafted as a starting point. Replace generic examples with verified case studies "
        "or proprietary data from your organisation before sharing externally.", muted))
    doc.build(flow)
    return buf.getvalue()
