"""Render a GeneratedDocument to PDF with one of four reportlab layouts.

Fonts are Windows TrueType fonts (embedded in the PDF) because reportlab's built-in
Helvetica has no rupee sign.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .spec import DISPLAYED_FIELDS, GeneratedDocument

FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
FONT_FILES: dict[str, tuple[str, str]] = {
    "Arial": ("arial.ttf", "arialbd.ttf"),
    "Times": ("times.ttf", "timesbd.ttf"),
    "Georgia": ("georgia.ttf", "georgiab.ttf"),
    "Verdana": ("verdana.ttf", "verdanab.ttf"),
}
MARGIN = 18 * mm


@dataclass(frozen=True)
class Look:
    font: str
    accent: colors.Color


LOOKS: dict[str, Look] = {
    "schedule_table": Look("Arial", colors.HexColor("#1F4E79")),
    "two_column": Look("Verdana", colors.HexColor("#7A1F1F")),
    "certificate": Look("Georgia", colors.HexColor("#2E5E3A")),
    "prose_deed": Look("Times", colors.black),
}

_registered: set[str] = set()


def _register(family: str) -> tuple[str, str]:
    regular, bold = f"{family}-Regular", f"{family}-Bold"
    if family not in _registered:
        reg_file, bold_file = FONT_FILES[family]
        pdfmetrics.registerFont(TTFont(regular, str(FONT_DIR / reg_file)))
        pdfmetrics.registerFont(TTFont(bold, str(FONT_DIR / bold_file)))
        _registered.add(family)
    return regular, bold


def _styles(look: Look) -> dict[str, ParagraphStyle]:
    regular, bold = _register(look.font)
    return {
        "title": ParagraphStyle("title", fontName=bold, fontSize=15, leading=19, alignment=TA_CENTER,
                                textColor=look.accent, spaceAfter=6),
        "insurer": ParagraphStyle("insurer", fontName=bold, fontSize=12, leading=15, alignment=TA_CENTER),
        "small": ParagraphStyle("small", fontName=regular, fontSize=8, leading=10, alignment=TA_CENTER),
        "h": ParagraphStyle("h", fontName=bold, fontSize=10, leading=13, spaceBefore=8, spaceAfter=3,
                            textColor=look.accent),
        "body": ParagraphStyle("body", fontName=regular, fontSize=9, leading=12.5, alignment=TA_JUSTIFY),
        "cell": ParagraphStyle("cell", fontName=regular, fontSize=9, leading=11.5),
        "cell_b": ParagraphStyle("cell_b", fontName=bold, fontSize=9, leading=11.5),
        "center": ParagraphStyle("center", fontName=regular, fontSize=10, leading=14, alignment=TA_CENTER),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _field_rows(doc: GeneratedDocument, skip: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    rows = []
    for field in DISPLAYED_FIELDS:
        shown = getattr(doc.displayed, field)
        if shown is not None and field not in skip:
            rows.append((shown.label, shown.text))
    return rows


def _kv_table(rows: list[tuple[str, str]], st: dict, look: Look, widths=(60 * mm, 112 * mm)) -> Table:
    data = [[_p(k, st["cell_b"]), _p(v, st["cell"])] for k, v in rows]
    table = Table(data, colWidths=list(widths))
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), 1.2, look.accent),
    ]))
    return table


def _header(doc: GeneratedDocument, st: dict) -> list:
    insurer = doc.displayed.insurer_name.text if doc.displayed.insurer_name else ""
    return [_p(insurer, st["insurer"]), _p(doc.insurer_address, st["small"]), Spacer(1, 6),
            _p(doc.title, st["title"])]


def _sections(doc: GeneratedDocument, st: dict) -> list:
    flow = []
    for section in doc.sections:
        flow += [_p(section.heading, st["h"]), _p(section.body, st["body"])]
    return flow


def _signature(doc: GeneratedDocument, st: dict) -> list:
    return [Spacer(1, 14), _p(doc.signatory, st["cell_b"])]


def _extra(doc: GeneratedDocument, st: dict, look: Look) -> list:
    rows = [(r.label, r.value) for r in doc.extra_rows]
    return [_p("Other Particulars", st["h"]), _kv_table(rows, st, look)] if rows else []


def _schedule_table(doc: GeneratedDocument, st: dict, look: Look) -> list:
    rows = _field_rows(doc, skip=("insurer_name",))
    return (_header(doc, st) + [_p(f"Address of Insured: {doc.insured_address}", st["cell"]), Spacer(1, 6),
            _kv_table(rows, st, look)] + _extra(doc, st, look) + _sections(doc, st) + _signature(doc, st))


def _two_column(doc: GeneratedDocument, st: dict, look: Look) -> list:
    party = [f for f in ("insured_name", "beneficiary") if getattr(doc.displayed, f)]
    policy = [f for f in ("policy_or_bond_number", "period_start", "period_end") if getattr(doc.displayed, f)]
    money = [f for f in ("sum_insured", "premium", "gst_amount") if getattr(doc.displayed, f)]

    def block(fields: list[str]) -> list:
        out = []
        for f in fields:
            shown = getattr(doc.displayed, f)
            out += [_p(shown.label, st["cell_b"]), _p(shown.text, st["cell"]), Spacer(1, 4)]
        return out

    left = [_p("INSURED", st["h"])] + block(party) + [_p(doc.insured_address, st["cell"])]
    right = [_p("POLICY", st["h"])] + block(policy)
    columns = Table([[left, right]], colWidths=[86 * mm, 86 * mm])
    columns.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, look.accent),
                                 ("INNERGRID", (0, 0), (-1, -1), 0.6, look.accent),
                                 ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    money_rows = [(getattr(doc.displayed, f).label, getattr(doc.displayed, f).text) for f in money]
    return (_header(doc, st) + [columns, _p("PREMIUM AND COVER", st["h"]), _kv_table(money_rows, st, look)]
            + _extra(doc, st, look) + _sections(doc, st) + _signature(doc, st))


def _certificate(doc: GeneratedDocument, st: dict, look: Look) -> list:
    flow = _header(doc, st) + [Spacer(1, 8)]
    for label, text in _field_rows(doc, skip=("insurer_name",)):
        flow.append(_p(f"{label}: {text}", st["center"]))
    flow.append(Spacer(1, 8))
    return flow + _extra(doc, st, look) + _sections(doc, st) + _signature(doc, st)


def _prose_deed(doc: GeneratedDocument, st: dict, look: Look) -> list:
    return _header(doc, st) + [Spacer(1, 6)] + _sections(doc, st) + _extra(doc, st, look) + _signature(doc, st)


LAYOUTS = {
    "schedule_table": _schedule_table,
    "two_column": _two_column,
    "certificate": _certificate,
    "prose_deed": _prose_deed,
}


def _border(look: Look):
    def draw(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(look.accent)
        canvas.setLineWidth(2)
        canvas.rect(10 * mm, 10 * mm, A4[0] - 20 * mm, A4[1] - 20 * mm)
        canvas.restoreState()
    return draw


def render_pdf(doc: GeneratedDocument, layout: str, path: Path) -> None:
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout {layout!r}")
    look = LOOKS[layout]
    st = _styles(look)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=MARGIN, title=doc.title,
                            author="PolicyLens synthetic dataset")
    on_page = _border(look) if layout == "certificate" else (lambda c, d: None)
    pdf.build(LAYOUTS[layout](doc, st, look), onFirstPage=on_page, onLaterPages=on_page)
