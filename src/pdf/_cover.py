"""Cover page builder for PDF commission statements."""
import os
from datetime import date

from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Spacer, Table, TableStyle, HRFlowable

from src.pdf._constants import CONTENT_W, CORAL, BORDER, BLACK, DIM
from src.pdf._helpers import _para, _style


def _cover_page(employee, period_label, logo_path):
    elements = []
    w = CONTENT_W

    # Logo or wordmark
    if logo_path and os.path.exists(logo_path):
        orig_w, orig_h = ImageReader(logo_path).getSize()
        logo_w = 25 * mm
        logo_h = logo_w * orig_h / orig_w
        img = Image(logo_path, width=logo_w, height=logo_h)
        img.hAlign = "LEFT"
        elements.append(img)
    else:
        elements.append(_para("NORMATIVE", _style(
            "logo", fontName="Helvetica-Bold", fontSize=20, textColor=CORAL, spaceAfter=4
        )))

    elements.append(Spacer(1, 22*mm))
    elements.append(HRFlowable(width=w, color=CORAL, thickness=2))
    elements.append(Spacer(1, 8*mm))

    elements.append(_para("COMMISSION STATEMENT", _style(
        "cover_title", fontName="Helvetica-Bold", fontSize=32, leading=40, textColor=BLACK, spaceAfter=6
    )))
    elements.append(_para(period_label, _style(
        "cover_period", fontName="Helvetica", fontSize=20, leading=26, textColor=DIM, spaceAfter=10
    )))
    elements.append(Spacer(1, 8*mm))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 8*mm))

    info = [
        ("Name",   employee.get("name", "")),
        ("Title",  employee.get("title", "")),
        ("Region", employee.get("region", "")),
    ]
    tbl = Table([[k + ":", v] for k, v in info], colWidths=[45*mm, w - 45*mm])
    tbl.setStyle(TableStyle([
        ("FONT",            (0, 0), (0, -1), "Helvetica-Bold", 12),
        ("FONT",            (1, 0), (1, -1), "Helvetica", 12),
        ("TEXTCOLOR",       (0, 0), (0, -1), DIM),
        ("TEXTCOLOR",       (1, 0), (1, -1), BLACK),
        ("TOPPADDING",      (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",   (0, 0), (-1, -1), 5),
        ("LEFTPADDING",     (0, 0), (-1, -1), 0),
    ]))
    elements.append(tbl)

    elements.append(Spacer(1, 40*mm))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 4*mm))
    elements.append(_para(
        f"Generated: {date.today().strftime('%d %B %Y')}   |   CONFIDENTIAL \u2014 For addressee only",
        _style("footer", fontName="Helvetica", fontSize=9, textColor=DIM)
    ))
    return elements
