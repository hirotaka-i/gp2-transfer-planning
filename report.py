"""
PDF report shared by the Stage 1 and Stage 2 apps.

Produces the document a cohort signs off and GP2 files: everything the person
typed, laid out the way the screens present it. Returns bytes so Streamlit can
hand it straight to st.download_button without touching the filesystem.
"""

from __future__ import annotations

import io
from datetime import date
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                               Spacer, Table, TableStyle)

ACCENT = colors.HexColor("#B04A3C")
GREY = colors.HexColor("#6B6B6B")
LINE = colors.HexColor("#D8D8D8")

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=_ss["Title"], fontSize=17, spaceAfter=2,
                    textColor=colors.black, alignment=0)
SUB = ParagraphStyle("SUB", parent=_ss["Normal"], fontSize=9, textColor=GREY,
                     spaceAfter=14)
H2 = ParagraphStyle("H2", parent=_ss["Heading2"], fontSize=12, spaceBefore=14,
                    spaceAfter=6, textColor=ACCENT)
BODY = ParagraphStyle("BODY", parent=_ss["Normal"], fontSize=9, leading=12.5)
NOTE = ParagraphStyle("NOTE", parent=BODY, fontSize=8, textColor=GREY)
CELL = ParagraphStyle("CELL", parent=BODY, fontSize=8.3, leading=10.5)
CELLH = ParagraphStyle("CELLH", parent=CELL, fontName="Helvetica-Bold")


def esc(v) -> str:
    """reportlab parses Paragraph text as XML, so `H&Y < 3` silently becomes
    `H&Y;`. Everything a user typed goes through here."""
    return escape("" if v is None or (isinstance(v, float) and pd.isna(v))
                  else str(v))


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(18 * mm, 12 * mm, doc.title)
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
    canvas.restoreState()


def fields(pairs: list[tuple[str, str]]) -> Table:
    """Two-column label/value block. Blank values are kept, not hidden — a gap
    in the record is information too."""
    rows = [[Paragraph(esc(k), CELLH),
             Paragraph(esc(v) if str(v).strip() else "—", CELL)]
            for k, v in pairs]
    t = Table(rows, colWidths=[52 * mm, TEXT_WIDTH - 52 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, LINE),
    ]))
    return t


TEXT_WIDTH = 174 * mm


def frame(df: pd.DataFrame, widths: list[float] | None = None,
          max_rows: int = 400) -> list:
    """A DataFrame as a table, truncated rather than allowed to run away.

    `widths` are RELATIVE weights, not absolute units — they are scaled to fill
    the text block. Passing absolute numbers here is the easy mistake: reportlab
    reads bare numbers as points, so a column meant to be 40 mm comes out 14 mm
    and the text wraps one character per line.
    """
    if df is None or df.empty:
        return [Paragraph("Nothing recorded.", NOTE)]
    shown = df.head(max_rows)
    head = [Paragraph(esc(c), CELLH) for c in shown.columns]
    body = [[Paragraph(esc(v), CELL) for v in row]
            for row in shown.itertuples(index=False)]
    if widths is None:
        widths = [1] * len(shown.columns)
    scale = TEXT_WIDTH / sum(widths)
    widths = [w * scale for w in widths]
    t = Table([head] + body, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
    ]))
    out = [t]
    if len(df) > max_rows:
        out.append(Paragraph(f"{len(df) - max_rows} further rows omitted — see the "
                             f"CSV export for the complete record.", NOTE))
    return out


def build(title: str, subtitle: str, sections: list[tuple[str, list]]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=20 * mm)
    story: list = [Paragraph(esc(title), H1), Paragraph(esc(subtitle), SUB)]
    for heading, content in sections:
        block = [Paragraph(esc(heading), H2)]
        # keep a heading with at least the start of its content
        story.append(KeepTogether(block + content[:1]))
        story.extend(content[1:])
        story.append(Spacer(1, 2))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def stamp(cohort: str) -> str:
    return (f"{cohort or 'Draft'} · generated {date.today().isoformat()} · "
            f"prototype, not a signed document")
