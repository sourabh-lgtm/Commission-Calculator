"""PDF commission statement generator using reportlab."""

import os
from datetime import date
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# Brand colours matching arr-dashboard design system
CORAL   = colors.HexColor("#FF9178")
GREEN   = colors.HexColor("#16a34a")
RED     = colors.HexColor("#dc2626")
DIM     = colors.HexColor("#595959")
BORDER  = colors.HexColor("#E0E0E0")
CARD_BG = colors.HexColor("#F5F5F5")
BLACK   = colors.black
WHITE   = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm


def generate_statement(
    employee: dict,
    month_str: str,          # "2026-02-01"
    summary: dict,           # from commission_detail row
    workings_rows: list[dict],
    accelerator: dict | None,
    output_path: str,
    logo_path: str | None = None,
) -> str:
    """Generate a PDF commission statement and save to output_path. Returns output_path."""

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    month_ts = date.fromisoformat(month_str)
    period_label = month_ts.strftime("%B %Y")  # "February 2026"
    currency = employee.get("currency", "EUR")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
    )

    styles = getSampleStyleSheet()
    story = []

    # ------------------------------------------------------------------
    # PAGE 1 — Cover
    # ------------------------------------------------------------------
    story.extend(_cover_page(employee, period_label, logo_path, styles))
    story.append(PageBreak())

    # ------------------------------------------------------------------
    # PAGE 2 — Commission Summary
    # ------------------------------------------------------------------
    story.extend(_summary_page(employee, period_label, summary, accelerator, currency, styles))
    story.append(PageBreak())

    # ------------------------------------------------------------------
    # PAGE 3+ — Full Workings
    # ------------------------------------------------------------------
    story.extend(_workings_page(employee, period_label, workings_rows, currency, styles))

    doc.build(story)
    return output_path


# ---------------------------------------------------------------------------
# Cover page
# ---------------------------------------------------------------------------

def _cover_page(employee, period_label, logo_path, styles):
    elements = []
    w = PAGE_W - 2 * MARGIN

    # Logo
    if logo_path and os.path.exists(logo_path):
        from reportlab.platypus import Image
        logo = Image(logo_path, width=40*mm, height=12*mm)
        elements.append(logo)
    else:
        elements.append(_para("NORMATIVE", ParagraphStyle(
            "logo", fontName="Helvetica-Bold", fontSize=18,
            textColor=CORAL, spaceAfter=4
        )))

    elements.append(Spacer(1, 30*mm))
    elements.append(HRFlowable(width=w, color=CORAL, thickness=2))
    elements.append(Spacer(1, 8*mm))

    elements.append(_para("COMMISSION STATEMENT", ParagraphStyle(
        "cover_title", fontName="Helvetica-Bold", fontSize=28,
        textColor=BLACK, spaceAfter=6
    )))
    elements.append(Spacer(1, 4*mm))
    elements.append(_para(period_label, ParagraphStyle(
        "cover_period", fontName="Helvetica", fontSize=18,
        textColor=DIM, spaceAfter=10
    )))
    elements.append(Spacer(1, 10*mm))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 10*mm))

    # Employee details
    info = [
        ("Name",   employee.get("name", "")),
        ("Title",  employee.get("title", "")),
        ("Region", employee.get("region", "")),
    ]
    tbl = Table([[k + ":", v] for k, v in info], colWidths=[40*mm, w - 40*mm])
    tbl.setStyle(TableStyle([
        ("FONT",     (0, 0), (0, -1), "Helvetica-Bold", 11),
        ("FONT",     (1, 0), (1, -1), "Helvetica", 11),
        ("TEXTCOLOR",(0, 0), (0, -1), DIM),
        ("TEXTCOLOR",(1, 0), (1, -1), BLACK),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    elements.append(tbl)

    elements.append(Spacer(1, 60*mm))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 4*mm))
    elements.append(_para(
        f"Generated: {date.today().strftime('%d %B %Y')}   |   CONFIDENTIAL — For addressee only",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=9, textColor=DIM)
    ))
    return elements


# ---------------------------------------------------------------------------
# Summary page
# ---------------------------------------------------------------------------

def _summary_page(employee, period_label, summary, accelerator, currency, styles):
    elements = []
    w = PAGE_W - 2 * MARGIN

    elements.append(_para(f"Commission Summary — {period_label}", ParagraphStyle(
        "h1", fontName="Helvetica-Bold", fontSize=16, textColor=BLACK, spaceAfter=4
    )))
    elements.append(_para(employee.get("name", ""), ParagraphStyle(
        "sub", fontName="Helvetica", fontSize=12, textColor=DIM, spaceAfter=12
    )))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 6*mm))

    sym = _sym(currency)

    def _fmt(v):
        if v is None:
            return "—"
        try:
            return f"{sym}{float(v):,.2f}"
        except Exception:
            return str(v)

    # Summary table data
    out_saos  = summary.get("outbound_sao_count", 0)
    in_saos   = summary.get("inbound_sao_count", 0)
    out_rate  = _rate_label(currency, "outbound")
    in_rate   = _rate_label(currency, "inbound")

    data = [
        ["Component", "Quantity", "Rate", f"Amount ({currency})"],
        ["Outbound SAOs",
         str(int(out_saos)),
         out_rate,
         _fmt(summary.get("outbound_sao_comm", 0))],
        ["Inbound SAOs",
         str(int(in_saos)),
         in_rate,
         _fmt(summary.get("inbound_sao_comm", 0))],
        ["Closed Won — Outbound (5% of ACV)",
         "—",
         f"ACV {_fmt(summary.get('outbound_cw_acv_eur', 0))} EUR × {summary.get('fx_rate', 1):.4f}",
         _fmt(summary.get("outbound_cw_comm", 0))],
        ["Closed Won — Inbound (1% of ACV)",
         "—",
         f"ACV {_fmt(summary.get('inbound_cw_acv_eur', 0))} EUR × {summary.get('fx_rate', 1):.4f}",
         _fmt(summary.get("inbound_cw_comm", 0))],
        ["Quarterly Accelerator Top-up",
         "—",
         _accel_desc(accelerator, currency),
         _fmt(summary.get("accelerator_topup", 0))],
        ["TOTAL COMMISSION", "", "", _fmt(summary.get("total_commission", 0))],
    ]

    col_widths = [75*mm, 20*mm, 55*mm, 30*mm]
    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",   (0, 0), (-1, 0), CORAL),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONT",         (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("ALIGN",        (1, 0), (-1, 0), "RIGHT"),
        # Body
        ("FONT",         (0, 1), (-1, -2), "Helvetica", 10),
        ("ALIGN",        (1, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("GRID",         (0, 0), (-1, -1), 0.5, BORDER),
        # Alternate rows
        ("BACKGROUND",   (0, 2), (-1, 2), CARD_BG),
        ("BACKGROUND",   (0, 4), (-1, 4), CARD_BG),
        # Total row
        ("BACKGROUND",   (0, -1), (-1, -1), colors.HexColor("#EEEEEE")),
        ("FONT",         (0, -1), (-1, -1), "Helvetica-Bold", 11),
        ("LINEABOVE",    (0, -1), (-1, -1), 1.5, BLACK),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 8*mm))

    # Quarterly SAO progress
    total_saos = int(summary.get("total_sao_count", 0))
    if accelerator:
        q_total = accelerator.get("total_saos", total_saos)
        threshold = accelerator.get("threshold", 9)
        elements.append(_para(
            f"Quarterly SAO Progress: {q_total} / {threshold} target"
            + (f" — Accelerator triggered ✓" if q_total > threshold else ""),
            ParagraphStyle("note", fontName="Helvetica", fontSize=10, textColor=DIM)
        ))

    elements.append(Spacer(1, 6*mm))
    elements.append(_para(
        "Payment is made on the last payroll date of the month following the month in which "
        "the payout becomes due. Subject to statutory deductions. Confidential.",
        ParagraphStyle("disclaimer", fontName="Helvetica", fontSize=8, textColor=DIM)
    ))
    return elements


# ---------------------------------------------------------------------------
# Workings page
# ---------------------------------------------------------------------------

def _workings_page(employee, period_label, rows, currency, styles):
    elements = []
    w = PAGE_W - 2 * MARGIN
    sym = _sym(currency)

    elements.append(_para(f"Full Commission Workings — {period_label}", ParagraphStyle(
        "h1", fontName="Helvetica-Bold", fontSize=14, textColor=BLACK, spaceAfter=4
    )))
    elements.append(_para(employee.get("name", ""), ParagraphStyle(
        "sub", fontName="Helvetica", fontSize=11, textColor=DIM, spaceAfter=8
    )))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 4*mm))

    if not rows:
        elements.append(_para("No qualifying activities this period.", ParagraphStyle(
            "empty", fontName="Helvetica", fontSize=10, textColor=DIM
        )))
        return elements

    header = ["Date", "Opportunity ID", "Type", "Category", "Rate / Formula", f"Commission ({currency})"]
    col_widths = [22*mm, 30*mm, 22*mm, 24*mm, 55*mm, 30*mm]
    data = [header]

    total = 0.0
    for r in rows:
        comm = float(r.get("commission", 0))
        total += comm
        data.append([
            r.get("date", ""),
            r.get("opportunity_id", ""),
            r.get("sao_type", "").title(),
            r.get("type", ""),
            r.get("rate_desc", ""),
            f"{sym}{comm:,.2f}",
        ])

    data.append(["", "", "", "", "TOTAL", f"{sym}{total:,.2f}"])

    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), CORAL),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONT",         (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT",         (0, 1), (-1, -2), "Helvetica", 9),
        ("FONT",         (0, -1), (-1, -1), "Helvetica-Bold", 9),
        ("ALIGN",        (5, 0), (5, -1), "RIGHT"),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",         (0, 0), (-1, -1), 0.4, BORDER),
        ("BACKGROUND",   (0, -1), (-1, -1), colors.HexColor("#EEEEEE")),
        ("LINEABOVE",    (0, -1), (-1, -1), 1, BLACK),
    ]))
    elements.append(tbl)
    return elements


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _para(text, style):
    return Paragraph(text, style)


def _sym(currency):
    return {"SEK": "kr ", "GBP": "£", "EUR": "€", "USD": "$"}.get(currency, "")


def _rate_label(currency, kind):
    from src.commission_plans.sdr import FIXED_RATES
    rates = FIXED_RATES.get(currency, FIXED_RATES["EUR"])
    key = "outbound_sao" if kind == "outbound" else "inbound_sao"
    sym = _sym(currency)
    return f"{sym}{rates[key]:,} / SAO"


def _accel_desc(accelerator, currency):
    if not accelerator or accelerator.get("accelerator_topup", 0) == 0:
        return "Not triggered (< 9 SAOs / quarter)"
    sym = _sym(currency)
    excess = accelerator.get("excess_outbound", 0)
    topup  = accelerator.get("topup_per_sao", 0)
    return f"{excess} excess outbound × {sym}{topup:,}"
