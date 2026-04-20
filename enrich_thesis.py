#!/usr/bin/env python3
"""HUNTER Thesis Enrichment -- AI-powered investment memo generation.

Usage: python enrich_thesis.py <hypothesis_id>
       python enrich_thesis.py all   # Enrich all diamonds
"""

import json
import os
import sys
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Flowable
)
from reportlab.pdfbase import pdfmetrics

from database import get_connection, init_db

load_dotenv(override=True)

# ============================================================
# Colours (matching the professional doc style)
# ============================================================
NAVY = HexColor("#1B2A4A")
ACCENT = HexColor("#2E5090")
LIGHT_BG = HexColor("#F5F6F8")
TEXT_DARK = HexColor("#2D2D2D")
SOURCE_GREY = HexColor("#888888")
BORDER_GREY = HexColor("#D0D3D9")
THESIS_BG = HexColor("#EEF1F6")
RED = HexColor("#C62828")

PAGE_W, PAGE_H = A4
MARGIN_L = 22 * mm
MARGIN_R = 22 * mm
MARGIN_T = 25 * mm
MARGIN_B = 22 * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

# ============================================================
# Styles
# ============================================================
S = {
    "body": ParagraphStyle("body", fontName="Times-Roman", fontSize=9.5, leading=14,
                           alignment=TA_JUSTIFY, spaceAfter=8, textColor=TEXT_DARK),
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=13, leading=18,
                         textColor=NAVY, spaceBefore=22, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                         textColor=ACCENT, spaceBefore=16, spaceAfter=8),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=9.5, leading=13,
                         textColor=TEXT_DARK, spaceBefore=12, spaceAfter=5),
    "thesis": ParagraphStyle("thesis", fontName="Times-Bold", fontSize=10, leading=14,
                             textColor=NAVY, alignment=TA_LEFT),
    "src": ParagraphStyle("src", fontName="Helvetica-Oblique", fontSize=7, leading=10,
                          textColor=SOURCE_GREY, spaceAfter=6),
    "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, leading=10,
                         textColor=white),
    "tc": ParagraphStyle("tc", fontName="Helvetica", fontSize=8, leading=10,
                         textColor=TEXT_DARK),
    "tcb": ParagraphStyle("tcb", fontName="Helvetica-Bold", fontSize=8, leading=10,
                          textColor=TEXT_DARK),
    "bullet": ParagraphStyle("bullet", fontName="Times-Roman", fontSize=9.5, leading=14,
                             alignment=TA_LEFT, leftIndent=14, firstLineIndent=-10,
                             spaceAfter=4, textColor=TEXT_DARK),
    "confidential": ParagraphStyle("conf", fontName="Helvetica-Bold", fontSize=6.5,
                                   textColor=RED, alignment=TA_LEFT),
}


# ============================================================
# Custom Flowables
# ============================================================
class ThesisBox(Flowable):
    """Navy-accent-bar bordered box for core thesis statement."""
    def __init__(self, text, width):
        Flowable.__init__(self)
        self.text = text
        self.box_width = width
        self.para = Paragraph(text, S["thesis"])
        self.para.wrapOn(None, width - 28, 1000)
        self.box_height = self.para.height + 24

    def wrap(self, availWidth, availHeight):
        return (self.box_width, self.box_height)

    def draw(self):
        c = self.canv
        c.setFillColor(THESIS_BG)
        c.setStrokeColor(BORDER_GREY)
        c.setLineWidth(0.5)
        c.roundRect(0, 0, self.box_width, self.box_height, 3, fill=1, stroke=1)
        c.setFillColor(NAVY)
        c.rect(0, 0, 3, self.box_height, fill=1, stroke=0)
        self.para.drawOn(c, 16, self.box_height - self.para.height - 12)


class KeyMetricBox(Flowable):
    """Row of metric boxes with navy accent bar."""
    def __init__(self, metrics, width):
        Flowable.__init__(self)
        self.metrics = metrics
        self.total_width = width
        self.box_height = 52

    def wrap(self, availWidth, availHeight):
        return (self.total_width, self.box_height)

    def draw(self):
        c = self.canv
        n = len(self.metrics)
        gap = 4
        bw = (self.total_width - (n - 1) * gap) / n
        for i, (label, value) in enumerate(self.metrics):
            x = i * (bw + gap)
            c.setFillColor(LIGHT_BG)
            c.setStrokeColor(BORDER_GREY)
            c.setLineWidth(0.5)
            c.roundRect(x, 0, bw, self.box_height, 2, fill=1, stroke=1)
            c.setFillColor(NAVY)
            c.rect(x, self.box_height - 2, bw, 2, fill=1, stroke=0)
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(NAVY)
            c.drawString(x + 10, 22, str(value))
            c.setFont("Helvetica", 7)
            c.setFillColor(SOURCE_GREY)
            c.drawString(x + 10, 10, str(label))


# ============================================================
# Cover page
# ============================================================
def draw_cover(canvas, doc, cover_data):
    c = canvas
    c.saveState()

    # Navy strip at top
    c.setFillColor(NAVY)
    c.rect(0, PAGE_H - 70 * mm, PAGE_W, 70 * mm, fill=1, stroke=0)

    # Confidential
    c.setFillColor(HexColor("#7A8BA8"))
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(MARGIN_L, PAGE_H - 18 * mm, "CONFIDENTIAL")

    # HUNTER RESEARCH
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN_L, PAGE_H - 30 * mm, "HUNTER")
    c.setFillColor(HexColor("#7A8BA8"))
    c.setFont("Helvetica", 9)
    c.drawString(MARGIN_L + 52, PAGE_H - 30 * mm, "RESEARCH")

    # Accent line
    c.setStrokeColor(ACCENT)
    c.setLineWidth(1.5)
    c.line(MARGIN_L, PAGE_H - 34 * mm, MARGIN_L + 100, PAGE_H - 34 * mm)

    # Tagline
    c.setFillColor(HexColor("#7A8BA8"))
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN_L, PAGE_H - 40 * mm, "Cross-Domain Intelligence  |  Systematic Research Platform")

    # Title
    y = PAGE_H - 95 * mm
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 24)
    # Word wrap title manually
    title = cover_data.get("title", "HUNTER Thesis")
    words = title.split()
    lines = []
    current = ""
    for w in words:
        test = current + " " + w if current else w
        if c.stringWidth(test, "Helvetica-Bold", 24) > CONTENT_W:
            lines.append(current)
            current = w
        else:
            current = test
    if current:
        lines.append(current)
    for line in lines:
        c.drawString(MARGIN_L, y, line)
        y -= 30

    # Subtitle
    y -= 5
    c.setFillColor(ACCENT)
    c.setFont("Times-Italic", 12)
    c.drawString(MARGIN_L, y, cover_data.get("subtitle", ""))

    # Accent line under subtitle
    y -= 12
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.5)
    c.line(MARGIN_L, y, MARGIN_L + 120, y)

    # Date, status, domains
    y -= 20
    c.setFillColor(TEXT_DARK)
    c.setFont("Helvetica", 9)
    c.drawString(MARGIN_L, y, cover_data.get("date", ""))
    y -= 14
    c.drawString(MARGIN_L, y, f"Status: {cover_data.get('status', 'Thesis Validated')}  |  Proprietary Research")
    y -= 14
    c.drawString(MARGIN_L, y, f"Domains: {cover_data.get('domains', '')}")

    # Methodology box near bottom
    box_y = 80 * mm
    box_h = 60
    c.setFillColor(LIGHT_BG)
    c.setStrokeColor(BORDER_GREY)
    c.setLineWidth(0.5)
    c.roundRect(MARGIN_L, box_y, CONTENT_W, box_h, 3, fill=1, stroke=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN_L + 12, box_y + box_h - 14, "METHODOLOGY")
    c.setFillColor(TEXT_DARK)
    c.setFont("Times-Roman", 7.5)
    method_text = "This thesis was identified by HUNTER, a systematic cross-domain research platform that monitors 18 distinct professional publication ecosystems, extracts structured model-vulnerability data, validates cross-domain causal connections, and subjects all surviving hypotheses to adversarial verification with live evidence. All facts are sourced from public filings, regulatory databases, and industry publications. Content has been independently validated."
    # Simple text wrapping
    words = method_text.split()
    line = ""
    ty = box_y + box_h - 28
    for w in words:
        test = line + " " + w if line else w
        if c.stringWidth(test, "Times-Roman", 7.5) > CONTENT_W - 24:
            c.drawString(MARGIN_L + 12, ty, line)
            ty -= 10
            line = w
        else:
            line = test
    if line:
        c.drawString(MARGIN_L + 12, ty, line)

    # Footer
    c.setFillColor(SOURCE_GREY)
    c.setFont("Helvetica", 6.5)
    c.drawString(MARGIN_L, 25 * mm, "CONFIDENTIAL  |  NOT INVESTMENT ADVICE  |  FOR RESEARCH PURPOSES ONLY")
    c.drawRightString(PAGE_W - MARGIN_R, 25 * mm, f"(c) {datetime.now().year} HUNTER Research")

    c.restoreState()


def draw_header_footer(canvas, doc, short_title):
    c = canvas
    c.saveState()
    # Header
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.75)
    c.line(MARGIN_L, PAGE_H - MARGIN_T + 8 * mm, PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 8 * mm)
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(MARGIN_L, PAGE_H - MARGIN_T + 10 * mm, "CONFIDENTIAL")
    c.setFillColor(SOURCE_GREY)
    c.setFont("Helvetica", 6.5)
    c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 10 * mm, f"HUNTER Research  |  {short_title}")

    # Footer
    c.setStrokeColor(SOURCE_GREY)
    c.setLineWidth(0.5)
    c.line(MARGIN_L, MARGIN_B - 4 * mm, PAGE_W - MARGIN_R, MARGIN_B - 4 * mm)
    c.setFont("Helvetica", 6.5)
    c.drawString(MARGIN_L, MARGIN_B - 8 * mm, "Proprietary & Confidential  |  Not Investment Advice")
    c.drawRightString(PAGE_W - MARGIN_R, MARGIN_B - 8 * mm, f"Page {doc.page}")
    c.restoreState()


# ============================================================
# AI Enrichment
# ============================================================
def enrich_hypothesis(hypothesis_text, diamond_score, domains, action_steps, full_report, fact_chain):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""Here is the raw thesis from an autonomous research system:

THESIS: {hypothesis_text}
DIAMOND SCORE: {diamond_score}/100
DOMAINS: {domains}
ACTION STEPS: {(action_steps or '')[:500]}
FACT CHAIN: {json.dumps(fact_chain)[:1000] if fact_chain else 'None'}
FULL REPORT: {(full_report or '')[:2000]}

Produce a structured investment memo with these exact sections:

1. TITLE: A compelling 3-8 word title for the thesis
2. SUBTITLE: One-line description in italics style
3. EXECUTIVE_SUMMARY: 2-3 paragraphs summarising the thesis, the asymmetry, and the trade
4. KEY_METRICS: Exactly 4 metrics as label|value pairs (e.g., "Primary Target|CLF", "Unmodelled Cost|$200-400M/yr")
5. THESIS_BOX: The core thesis statement in 2-3 bold sentences
6. TRADE: How to execute this (entry, catalyst, timeframe, exit)
7. BLIND_SPOTS: 2-4 blind spots, each with a title, 1-2 paragraphs, "The audience:" line, and sources
8. EVIDENCE: Specific facts, filings, dates that support the thesis
9. RISK_CASE: What kills this thesis - 3-5 specific risks with severity (High/Medium/Low)
10. MONITORING: What to watch monthly/quarterly
11. VERDICT: One-line final assessment

Be specific. Name companies. Name people. Cite specific filings, dates, regulatory decisions. If you don't know something precisely, say so.

Respond with ONLY a JSON object with these exact keys:
{{
    "title": "...",
    "subtitle": "...",
    "executive_summary": "...",
    "key_metrics": [["label1", "value1"], ["label2", "value2"], ["label3", "value3"], ["label4", "value4"]],
    "thesis_box": "...",
    "trade": "...",
    "blind_spots": [
        {{"title": "...", "body": "...", "audience": "...", "sources": "..."}},
        ...
    ],
    "evidence": "...",
    "risk_case": [
        {{"risk": "...", "severity": "High/Medium/Low", "detail": "..."}},
        ...
    ],
    "monitoring": "...",
    "verdict": "..."
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        temperature=0.3,
        system="You are a senior investment analyst at a top-tier fund. You receive raw investment thesis signals from an autonomous research system. Your job is to enrich them into professional investment memos. Be specific. Name companies. Name people. Cite specific filings, dates, regulatory decisions. If you don't know something precisely, say so - do not fabricate.",
        messages=[{"role": "user", "content": prompt}],
    )

    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


# ============================================================
# PDF Builder
# ============================================================
def build_pdf(filename, cover_data, enriched, short_title):
    doc = SimpleDocTemplate(
        filename, pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
    )

    story = []
    # Cover page is drawn by canvas callback; start with spacer + page break
    story.append(Spacer(1, 1))
    story.append(PageBreak())

    # Executive Summary
    story.append(Paragraph("Executive Summary", S["h1"]))
    story.append(KeyMetricBox(enriched.get("key_metrics", [])[:4], CONTENT_W))
    story.append(Spacer(1, 8))
    for para in enriched.get("executive_summary", "").split("\n\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), S["body"]))

    # Thesis box
    story.append(Spacer(1, 8))
    story.append(ThesisBox(enriched.get("thesis_box", ""), CONTENT_W))
    story.append(Spacer(1, 8))

    # Trade
    story.append(Paragraph(f"<b>The trade:</b> {enriched.get('trade', '')}", S["body"]))

    # Blind Spots
    blind_spots = enriched.get("blind_spots", [])
    if blind_spots:
        story.append(Paragraph("The Blind Spots", S["h1"]))
        for i, bs in enumerate(blind_spots, 1):
            story.append(Paragraph(f"Blind Spot {i}: {bs.get('title', '')}", S["h2"]))
            for para in bs.get("body", "").split("\n\n"):
                if para.strip():
                    story.append(Paragraph(para.strip(), S["body"]))
            if bs.get("audience"):
                story.append(Paragraph(f"<b>The audience:</b> {bs['audience']}", S["body"]))
            if bs.get("sources"):
                story.append(Paragraph(f"Sources: {bs['sources']}", S["src"]))

    # Evidence
    if enriched.get("evidence"):
        story.append(Paragraph("Evidence Base", S["h1"]))
        for para in enriched["evidence"].split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), S["body"]))

    # Risk Case
    risks = enriched.get("risk_case", [])
    if risks:
        story.append(Paragraph("Risk Analysis", S["h1"]))
        risk_data = [
            [Paragraph("Risk", S["th"]), Paragraph("Severity", S["th"]), Paragraph("Detail", S["th"])]
        ]
        for r in risks:
            sev = r.get("severity", "Medium")
            sev_color = HexColor("#C62828") if sev == "High" else HexColor("#F59E0B") if sev == "Medium" else HexColor("#059669")
            risk_data.append([
                Paragraph(r.get("risk", ""), S["tcb"]),
                Paragraph(f'<font color="{sev_color.hexval()}">{sev}</font>', S["tc"]),
                Paragraph(r.get("detail", ""), S["tc"]),
            ])
        risk_table = Table(risk_data, colWidths=[CONTENT_W * 0.28, CONTENT_W * 0.12, CONTENT_W * 0.60])
        risk_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER_GREY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        # Alternating row backgrounds
        for i in range(1, len(risk_data)):
            if i % 2 == 0:
                risk_table.setStyle(TableStyle([("BACKGROUND", (0, i), (-1, i), LIGHT_BG)]))
        story.append(risk_table)

    # Monitoring
    if enriched.get("monitoring"):
        story.append(Paragraph("Monitoring Protocol", S["h1"]))
        for para in enriched["monitoring"].split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), S["body"]))

    # Verdict
    if enriched.get("verdict"):
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"<b>Verdict:</b> {enriched['verdict']}", S["body"]))

    # Disclosure page
    story.append(PageBreak())
    story.append(Spacer(1, 40))
    story.append(Paragraph("IMPORTANT DISCLOSURES", S["h1"]))
    story.append(Paragraph(
        "This document was produced by HUNTER, an autonomous cross-domain research platform. "
        "It is provided for informational and research purposes only and does not constitute "
        "investment advice, a recommendation, or a solicitation to buy or sell any security.",
        S["body"]
    ))
    story.append(Paragraph(
        "All facts cited are sourced from public filings, regulatory databases, and industry "
        "publications. The analysis has been subjected to adversarial verification including "
        "fact-checking, competitor analysis, barrier analysis, and market awareness testing. "
        "Despite this verification, errors may exist and market conditions may change.",
        S["body"]
    ))
    story.append(Paragraph(
        f"(c) {datetime.now().year} HUNTER Research. All rights reserved. "
        "Proprietary and confidential. Do not distribute without permission.",
        S["src"]
    ))

    def on_first_page(canvas, doc):
        draw_cover(canvas, doc, cover_data)

    def on_later_pages(canvas, doc):
        draw_header_footer(canvas, doc, short_title)

    doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_pages)


# ============================================================
# Main
# ============================================================
def process_hypothesis(hyp_id):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hypotheses WHERE id = ?", (hyp_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"Hypothesis #{hyp_id} not found")
        return

    h = dict(row)
    print(f"Enriching #{hyp_id} (score {h.get('diamond_score', '?')})...")

    # Parse fact chain
    fact_chain = []
    try:
        fact_chain = json.loads(h.get("fact_chain", "[]") or "[]")
    except: pass

    # Get domains from collision
    domains = ""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT domains_involved FROM collisions WHERE id = ?", (h.get("collision_id"),))
        coll = cursor.fetchone()
        if coll:
            domains = coll["domains_involved"]
        conn.close()
    except: pass

    # Enrich with AI
    enriched = enrich_hypothesis(
        hypothesis_text=h.get("hypothesis_text", ""),
        diamond_score=h.get("diamond_score", 0),
        domains=domains,
        action_steps=h.get("action_steps", ""),
        full_report=h.get("full_report", ""),
        fact_chain=fact_chain,
    )

    # Build PDF
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    filename = os.path.join(reports_dir, f"HUNTER_Thesis_{hyp_id}.pdf")

    title = enriched.get("title", f"Thesis #{hyp_id}")
    subtitle = enriched.get("subtitle", "A Cross-Domain Intelligence Thesis")

    cover_data = {
        "title": title,
        "subtitle": subtitle,
        "date": datetime.now().strftime("%d %B %Y"),
        "status": "Thesis Validated",
        "domains": domains or "Cross-Domain",
    }

    short_title = title[:40]

    build_pdf(filename, cover_data, enriched, short_title)
    print(f"PDF generated: {filename}")
    return filename


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python enrich_thesis.py <hypothesis_id>")
        print("       python enrich_thesis.py all")
        sys.exit(1)

    if sys.argv[1].lower() == "all":
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM hypotheses WHERE survived_kill = 1 AND diamond_score >= 50 ORDER BY diamond_score DESC")
        ids = [r["id"] for r in cursor.fetchall()]
        conn.close()
        print(f"Enriching {len(ids)} diamond hypotheses...")
        for hyp_id in ids:
            try:
                process_hypothesis(hyp_id)
            except Exception as e:
                print(f"Error on #{hyp_id}: {e}")
    else:
        try:
            hyp_id = int(sys.argv[1])
            process_hypothesis(hyp_id)
        except ValueError:
            print(f"Invalid hypothesis ID: {sys.argv[1]}")
            sys.exit(1)
