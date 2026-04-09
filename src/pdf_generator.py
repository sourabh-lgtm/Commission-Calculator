"""PDF commission statement generator using reportlab — landscape A4."""

import os
from datetime import date
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# Brand colours matching arr-dashboard design system
CORAL   = colors.HexColor("#FF9178")
GREEN   = colors.HexColor("#16a34a")
PURPLE  = colors.HexColor("#7c3aed")
RED     = colors.HexColor("#dc2626")
DIM     = colors.HexColor("#595959")
BORDER  = colors.HexColor("#E0E0E0")
CARD_BG = colors.HexColor("#F5F5F5")
BLACK   = colors.black
WHITE   = colors.white

# Landscape A4: 297 × 210 mm  →  usable width = 297 - 2×20 = 257 mm
PAGE_W, PAGE_H = landscape(A4)
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN   # 257 mm


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
    period_label = month_ts.strftime("%B %Y")   # "February 2026"
    currency = employee.get("currency", "EUR")
    role = employee.get("role", "sdr")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
    )

    story = []

    # ------------------------------------------------------------------
    # PAGE 1 — Cover (shared)
    # ------------------------------------------------------------------
    story.extend(_cover_page(employee, period_label, logo_path))
    story.append(PageBreak())

    # ------------------------------------------------------------------
    # PAGE 2 — Summary  (role-specific)
    # ------------------------------------------------------------------
    if role == "cs":
        story.extend(_cs_summary_page(employee, period_label, summary, currency))
    elif role == "ae":
        story.extend(_ae_summary_page(employee, period_label, summary, accelerator, currency))
    else:
        story.extend(_summary_page(employee, period_label, summary, accelerator, currency))
    story.append(PageBreak())

    # ------------------------------------------------------------------
    # PAGE 3+ — Full Workings  (role-specific)
    # ------------------------------------------------------------------
    if role == "cs":
        story.extend(_cs_workings_page(employee, period_label, workings_rows, summary, currency))
    elif role == "ae":
        story.extend(_ae_workings_page(employee, period_label, workings_rows, accelerator, currency))
    else:
        story.extend(_workings_page(employee, period_label, workings_rows, currency))

    doc.build(story)
    return output_path


# ---------------------------------------------------------------------------
# Cover page
# ---------------------------------------------------------------------------

def _cover_page(employee, period_label, logo_path):
    elements = []
    w = CONTENT_W

    # Logo or wordmark
    if logo_path and os.path.exists(logo_path):
        from reportlab.platypus import Image
        elements.append(Image(logo_path, width=50*mm, height=15*mm))
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
        f"Generated: {date.today().strftime('%d %B %Y')}   |   CONFIDENTIAL — For addressee only",
        _style("footer", fontName="Helvetica", fontSize=9, textColor=DIM)
    ))
    return elements


# ---------------------------------------------------------------------------
# Summary page
# ---------------------------------------------------------------------------

def _summary_page(employee, period_label, summary, accelerator, currency):
    elements = []
    w = CONTENT_W
    sym = _sym(currency)

    elements.append(_para(f"Commission Summary — {period_label}", _style(
        "h1", fontName="Helvetica-Bold", fontSize=16, textColor=BLACK, spaceAfter=4
    )))
    elements.append(_para(employee.get("name", ""), _style(
        "sub", fontName="Helvetica", fontSize=12, textColor=DIM, spaceAfter=10
    )))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 5*mm))

    def _fmt(v):
        if v is None or v == "":
            return "—"
        try:
            f = float(v)
            return f"{sym}{f:,.2f}" if f != 0 else "—"
        except Exception:
            return str(v)

    fx = summary.get("fx_rate", 1) or 1

    out_saos = int(summary.get("outbound_sao_count", 0) or 0)
    in_saos  = int(summary.get("inbound_sao_count", 0) or 0)
    spif_amt = float(summary.get("spif_amount", 0) or 0)

    rows = [
        ["Component", "Qty", "Rate / Basis", f"Amount ({currency})"],
        ["Outbound SAOs",
         str(out_saos),
         _rate_label(currency, "outbound"),
         _fmt(summary.get("outbound_sao_comm", 0))],
        ["Inbound SAOs",
         str(in_saos),
         _rate_label(currency, "inbound"),
         _fmt(summary.get("inbound_sao_comm", 0))],
        ["Closed Won — Outbound (5% ACV)",
         "—",
         f"ACV {sym}{_num(summary.get('outbound_cw_acv_eur', 0))} EUR × {fx:.4f}",
         _fmt(summary.get("outbound_cw_comm", 0))],
        ["Closed Won — Inbound (1% ACV)",
         "—",
         f"ACV {sym}{_num(summary.get('inbound_cw_acv_eur', 0))} EUR × {fx:.4f}",
         _fmt(summary.get("inbound_cw_comm", 0))],
        ["Quarterly Accelerator Top-up",
         "—",
         _accel_desc(accelerator, currency),
         _fmt(summary.get("accelerator_topup", 0))],
    ]

    # SPIF row (only if non-zero)
    if spif_amt:
        rows.append(["SPIF Award", "—", "Sales Performance Incentive", _fmt(spif_amt)])

    rows.append(["TOTAL COMMISSION", "", "", _fmt(summary.get("total_commission", 0))])

    total_row_idx = len(rows) - 1
    spif_row_idx  = total_row_idx - 1 if spif_amt else None

    # Column widths: Component | Qty | Rate/Basis | Amount  (sum = CONTENT_W)
    col_w = [100*mm, 18*mm, w - 100*mm - 18*mm - 40*mm, 40*mm]

    tbl = Table(rows, colWidths=col_w)
    style_cmds = [
        # Header
        ("BACKGROUND",    (0, 0), (-1, 0), CORAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONT",          (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("ALIGN",         (1, 0), (-1, 0), "RIGHT"),
        # Body
        ("FONT",          (0, 1), (-1, total_row_idx - 1), "Helvetica", 10),
        ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, BORDER),
        # Alternate rows
        ("BACKGROUND",    (0, 2), (-1, 2), CARD_BG),
        ("BACKGROUND",    (0, 4), (-1, 4), CARD_BG),
        # Total row
        ("BACKGROUND",    (0, total_row_idx), (-1, total_row_idx), colors.HexColor("#EEEEEE")),
        ("FONT",          (0, total_row_idx), (-1, total_row_idx), "Helvetica-Bold", 11),
        ("LINEABOVE",     (0, total_row_idx), (-1, total_row_idx), 1.5, BLACK),
    ]
    # SPIF row highlighted in purple
    if spif_row_idx is not None:
        style_cmds += [
            ("TEXTCOLOR",  (0, spif_row_idx), (-1, spif_row_idx), PURPLE),
            ("FONT",       (0, spif_row_idx), (-1, spif_row_idx), "Helvetica-Bold", 10),
        ]

    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    elements.append(Spacer(1, 6*mm))

    # Quarterly SAO progress note
    if accelerator:
        q_total   = accelerator.get("total_saos", int(summary.get("total_sao_count", 0)))
        threshold = accelerator.get("threshold", 9)
        note = f"Quarterly SAO Progress: {q_total} / {threshold} target"
        if q_total > threshold:
            note += "  — Accelerator triggered ✓"
        elements.append(_para(note, _style("note", fontName="Helvetica", fontSize=10, textColor=DIM)))
        elements.append(Spacer(1, 4*mm))

    elements.append(_para(
        "Payment is made on the last payroll date of the month following the month in which "
        "the payout becomes due. Subject to statutory deductions. Confidential.",
        _style("disc", fontName="Helvetica", fontSize=8, textColor=DIM)
    ))
    return elements


# ---------------------------------------------------------------------------
# Workings page
# ---------------------------------------------------------------------------

def _workings_page(employee, period_label, rows, currency):
    elements = []
    w = CONTENT_W
    sym = _sym(currency)

    elements.append(_para(f"Full Commission Workings — {period_label}", _style(
        "h1", fontName="Helvetica-Bold", fontSize=14, textColor=BLACK, spaceAfter=4
    )))
    elements.append(_para(employee.get("name", ""), _style(
        "sub", fontName="Helvetica", fontSize=11, textColor=DIM, spaceAfter=8
    )))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 4*mm))

    if not rows:
        elements.append(_para("No qualifying activities this period.", _style(
            "empty", fontName="Helvetica", fontSize=10, textColor=DIM
        )))
        return elements

    # Column widths (total = CONTENT_W = 257mm):
    # Date | Opportunity Name | Direction | Category | Rate/Formula | Commission
    col_w = [22*mm, 95*mm, 22*mm, 26*mm, w - 22*mm - 95*mm - 22*mm - 26*mm - 36*mm, 36*mm]

    header = ["Date", "Opportunity / Deal", "Direction", "Category", "Rate / Formula", f"Commission ({currency})"]
    data = [header]

    _cell_style = ParagraphStyle("wk_cell", fontName="Helvetica", fontSize=9, leading=11)
    _spif_style = ParagraphStyle("wk_spif", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=PURPLE)

    total = 0.0
    spif_row_indices = []

    for i, r in enumerate(rows, start=1):
        comm      = float(r.get("commission", 0))
        total    += comm
        row_type  = r.get("type", "")
        is_spif   = row_type == "SPIF"

        # Opportunity label: prefer name, fall back to ID
        opp = r.get("opportunity_name") or r.get("opportunity_id", "")
        if is_spif:
            opp = r.get("opportunity_name") or r.get("description", opp)

        doc_num  = r.get("document_number", "")
        opp_text = f"{opp}<br/>{doc_num}" if doc_num else str(opp)
        opp_cell = Paragraph(opp_text, _spif_style if is_spif else _cell_style)

        direction = (r.get("sao_type") or "").title()
        rate_desc = r.get("rate_desc", "") if not is_spif else "SPIF Award"
        comm_str  = f"{sym}{comm:,.2f}"

        data.append([
            r.get("date", ""),
            opp_cell,
            direction,
            row_type,
            rate_desc,
            comm_str,
        ])

        if is_spif:
            spif_row_indices.append(i)

    data.append(["", "", "", "", "TOTAL", f"{sym}{total:,.2f}"])
    total_row_idx = len(data) - 1

    tbl = Table(data, colWidths=col_w)

    style_cmds = [
        # Header
        ("BACKGROUND",    (0, 0), (-1, 0), CORAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONT",          (0, 0), (-1, 0), "Helvetica-Bold", 9),
        # Body
        ("FONT",          (0, 1), (-1, total_row_idx - 1), "Helvetica", 9),
        ("ALIGN",         (5, 0), (5, -1), "RIGHT"),
        ("ALIGN",         (4, total_row_idx), (4, total_row_idx), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (5, 0), (5, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        # Alternate body rows
        *[("BACKGROUND", (0, i), (-1, i), CARD_BG)
          for i in range(1, total_row_idx) if i % 2 == 0],
        # Total row
        ("BACKGROUND",    (0, total_row_idx), (-1, total_row_idx), colors.HexColor("#EEEEEE")),
        ("FONT",          (0, total_row_idx), (-1, total_row_idx), "Helvetica-Bold", 9),
        ("LINEABOVE",     (0, total_row_idx), (-1, total_row_idx), 1, BLACK),
    ]

    # Highlight SPIF rows in purple
    for idx in spif_row_indices:
        style_cmds += [
            ("TEXTCOLOR", (0, idx), (-1, idx), PURPLE),
            ("FONT",      (0, idx), (-1, idx), "Helvetica-Bold", 9),
        ]

    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    return elements


# ---------------------------------------------------------------------------
# CS summary page
# ---------------------------------------------------------------------------

def _cs_summary_page(employee, period_label, summary, currency):
    elements = []
    w = CONTENT_W
    sym = _sym(currency)

    elements.append(_para(f"Bonus Summary — {period_label}", _style(
        "h1", fontName="Helvetica-Bold", fontSize=16, textColor=BLACK, spaceAfter=4
    )))
    elements.append(_para(employee.get("name", ""), _style(
        "sub", fontName="Helvetica", fontSize=12, textColor=DIM, spaceAfter=10
    )))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 5*mm))

    def _fmt(v):
        if v is None or v == "" or v == 0:
            return "—"
        try:
            f = float(v)
            return f"{sym}{f:,.2f}" if f != 0 else "—"
        except Exception:
            return str(v)

    def _pct(v):
        try:
            return f"{float(v):.1f}%" if v else "—"
        except Exception:
            return "—"

    nrr_pct          = float(summary.get("nrr_pct", 0) or 0)
    csat_pct         = float(summary.get("csat_score_pct", 0) or 0)
    credits_pct      = float(summary.get("credits_used_pct", 0) or 0)
    q_target         = float(summary.get("quarterly_bonus_target", 0) or 0)
    nrr_bonus        = float(summary.get("nrr_bonus", 0) or 0)
    csat_bonus       = float(summary.get("csat_bonus", 0) or 0)
    credits_bonus    = float(summary.get("credits_bonus", 0) or 0)
    accel_topup      = float(summary.get("accelerator_topup", 0) or 0)
    ref_sao_count    = int(summary.get("referral_sao_count", 0) or 0)
    ref_sao_comm     = float(summary.get("referral_sao_comm", 0) or 0)
    ref_cw_comm      = float(summary.get("referral_cw_comm", 0) or 0)
    total            = float(summary.get("total_commission", 0) or 0)

    # NRR tier description
    nrr_tier = "< 90% → 0%"
    for lo, hi, frac in [(90,92,50),(92,94,60),(94,96,70),(96,98,80),(98,100,90),(100,101,100)]:
        if lo <= nrr_pct < hi:
            nrr_tier = f"{lo}–{hi}% band → {frac}% payout"; break
    if nrr_pct >= 100:
        nrr_tier = "≥ 100% → 100% payout"

    # CSAT tier description
    if csat_pct < 80:
        csat_tier = "< 80% → 0%"
    elif csat_pct < 90:
        csat_tier = "80–90% → 50% payout"
    else:
        csat_tier = "≥ 90% → 100% payout"

    # Credits tier description
    if credits_pct < 50:
        credits_tier = "< 50% → 0%"
    elif credits_pct < 75:
        credits_tier = "50–75% → 50% payout"
    elif credits_pct < 100:
        credits_tier = "75–100% → 75% payout"
    else:
        credits_tier = "≥ 100% → 100% payout"

    is_q_end = q_target > 0

    rows: list[list] = [["Component", "Score / Qty", "Rate / Basis", f"Amount ({currency})"]]

    if is_q_end:
        rows += [
            ["Quarterly Bonus Target", "—", "15% × annual salary ÷ 4", _fmt(q_target)],
            ["NRR (50% weight)", _pct(nrr_pct), nrr_tier, _fmt(nrr_bonus)],
            ["CSAT (35% weight)", _pct(csat_pct), csat_tier, _fmt(csat_bonus)],
            ["Service Credits (15% weight)", _pct(credits_pct), credits_tier, _fmt(credits_bonus)],
        ]
        if accel_topup:
            excess = round(nrr_pct - 100, 2) if nrr_pct > 100 else 0
            rows.append(["NRR Accelerator Top-up", f"+{excess:.1f}% above 100%",
                         "+2% of NRR portion per 1% above 100%", _fmt(accel_topup)])

    if ref_sao_count:
        rows.append(["Referral SAO Commissions",
                     f"{ref_sao_count} referral{'s' if ref_sao_count != 1 else ''}",
                     "Fixed rate per referral confirmed as SAO", _fmt(ref_sao_comm)])
    if ref_cw_comm:
        rows.append(["Referral Closed-Won Comm", "—", "5% / 1% of ACV (outbound / inbound)", _fmt(ref_cw_comm)])

    rows.append(["TOTAL PAYOUT", "", "", _fmt(total)])
    total_row_idx = len(rows) - 1

    col_w = [100*mm, 32*mm, w - 100*mm - 32*mm - 40*mm, 40*mm]
    tbl = Table(rows, colWidths=col_w)

    style_cmds = [
        ("BACKGROUND",  (0, 0), (-1, 0), CORAL),
        ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
        ("FONT",        (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("ALIGN",       (1, 0), (-1, 0), "RIGHT"),
        ("FONT",        (0, 1), (-1, total_row_idx - 1), "Helvetica", 10),
        ("ALIGN",       (1, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0,0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("GRID",        (0, 0), (-1, -1), 0.5, BORDER),
        *[("BACKGROUND", (0, i), (-1, i), CARD_BG) for i in range(1, total_row_idx) if i % 2 == 0],
        ("BACKGROUND",  (0, total_row_idx), (-1, total_row_idx), colors.HexColor("#EEEEEE")),
        ("FONT",        (0, total_row_idx), (-1, total_row_idx), "Helvetica-Bold", 11),
        ("LINEABOVE",   (0, total_row_idx), (-1, total_row_idx), 1.5, BLACK),
    ]
    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    elements.append(Spacer(1, 6*mm))

    if not is_q_end:
        elements.append(_para(
            "Quarterly bonus (NRR, CSAT, Service Credits) is paid in quarter-end months only "
            "(March, June, September, December).",
            _style("note", fontName="Helvetica", fontSize=10, textColor=DIM)
        ))
        elements.append(Spacer(1, 4*mm))

    elements.append(_para(
        "Payment is made on the last payroll date of the month following the month in which "
        "the payout becomes due. Subject to statutory deductions. Confidential.",
        _style("disc", fontName="Helvetica", fontSize=8, textColor=DIM)
    ))
    return elements


# ---------------------------------------------------------------------------
# CS workings page
# ---------------------------------------------------------------------------

def _cs_workings_page(employee, period_label, rows, summary, currency):
    elements = []
    w = CONTENT_W
    sym = _sym(currency)

    elements.append(_para(f"Bonus Workings — {period_label}", _style(
        "h1", fontName="Helvetica-Bold", fontSize=14, textColor=BLACK, spaceAfter=4
    )))
    elements.append(_para(employee.get("name", ""), _style(
        "sub", fontName="Helvetica", fontSize=11, textColor=DIM, spaceAfter=8
    )))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 4*mm))

    if not rows:
        elements.append(_para("No qualifying activities this period.", _style(
            "empty", fontName="Helvetica", fontSize=10, textColor=DIM
        )))
        return elements

    # Bonus amounts for quarterly rows (backend sets commission=None on these)
    _bonus_amts = {
        "CS Bonus \u2014 NRR (50%)":             float(summary.get("nrr_bonus", 0) or 0),
        "CS Bonus \u2014 CSAT (35%)":            float(summary.get("csat_bonus", 0) or 0),
        "CS Bonus \u2014 Service Credits (15%)": float(summary.get("credits_bonus", 0) or 0),
    }

    # Column widths: Date | Component | Account/Period | Rate/Tier | Amount
    col_w = [22*mm, 62*mm, 75*mm, w - 22*mm - 62*mm - 75*mm - 36*mm, 36*mm]
    header = ["Date", "Component", "Account / Period", "Rate / Tier", f"Amount ({currency})"]
    data = [header]

    _cell_style  = ParagraphStyle("cs_wk_cell",  fontName="Helvetica",      fontSize=9, leading=11)
    _bonus_style = ParagraphStyle("cs_wk_bonus", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=CORAL)
    _fcst_style  = ParagraphStyle("cs_wk_fcst",  fontName="Helvetica",      fontSize=9, leading=11, textColor=DIM)
    _acct_style  = ParagraphStyle("cs_wk_acct",  fontName="Helvetica",      fontSize=8, leading=10, textColor=DIM)
    _acct_b_style = ParagraphStyle("cs_wk_acctb", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=DIM)

    total = 0.0
    bonus_row_indices = []
    acct_row_indices  = []

    for i, r in enumerate(rows, start=1):
        row_type    = r.get("type", "")
        is_bonus    = row_type in _bonus_amts
        is_forecast = bool(r.get("is_forecast", False))
        is_acct     = row_type == "CS NRR Account"

        comm = _bonus_amts.get(row_type) if is_bonus else (float(r.get("commission") or 0))
        # Account sub-rows show net impact but don't add to commission total
        if not is_acct:
            total += 0.0 if is_forecast else comm

        account   = r.get("opportunity_name") or r.get("opportunity_id", "")
        rate_desc = r.get("rate_desc", "") or ""

        # Surface ACV and FX inline for closed-won referral rows
        if r.get("acv_eur") and r.get("fx_rate"):
            rate_desc = (f"ACV {_sym('EUR')}{_num(r['acv_eur'])} EUR "
                         f"\u00d7 {float(r['fx_rate']):.4f} \u2192 {rate_desc}")

        if is_acct:
            comm_str = f"{comm:+,.0f}" if comm else "—"
            data.append([
                "",
                Paragraph("  ↳", _acct_style),
                Paragraph(str(account), _acct_b_style),
                Paragraph(rate_desc, _acct_style),
                comm_str,
            ])
            acct_row_indices.append(i)
        elif is_bonus:
            comm_str = f"{sym}{comm:,.2f}" if comm else "—"
            cell_s = _bonus_style
            data.append([
                r.get("date", ""),
                Paragraph(row_type, cell_s),
                Paragraph(str(account), _cell_style),
                Paragraph(rate_desc, _cell_style),
                comm_str,
            ])
            bonus_row_indices.append(i)
        elif is_forecast:
            comm_str = f"{sym}{comm:,.2f} (forecast)"
            data.append([
                r.get("date", ""),
                Paragraph(row_type, _fcst_style),
                Paragraph(str(account), _cell_style),
                Paragraph(rate_desc, _cell_style),
                comm_str,
            ])
        else:
            comm_str = f"{sym}{comm:,.2f}"
            data.append([
                r.get("date", ""),
                Paragraph(row_type, _cell_style),
                Paragraph(str(account), _cell_style),
                Paragraph(rate_desc, _cell_style),
                comm_str,
            ])

    data.append(["", "", "", "TOTAL", f"{sym}{total:,.2f}"])
    total_row_idx = len(data) - 1

    tbl = Table(data, colWidths=col_w)
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), CORAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONT",          (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT",          (0, 1), (-1, total_row_idx - 1), "Helvetica", 9),
        ("ALIGN",         (4, 0), (4, -1), "RIGHT"),
        ("ALIGN",         (3, total_row_idx), (3, total_row_idx), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (4, 0), (4, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        *[("BACKGROUND", (0, i), (-1, i), CARD_BG) for i in range(1, total_row_idx) if i % 2 == 0],
        ("BACKGROUND",    (0, total_row_idx), (-1, total_row_idx), colors.HexColor("#EEEEEE")),
        ("FONT",          (0, total_row_idx), (-1, total_row_idx), "Helvetica-Bold", 9),
        ("LINEABOVE",     (0, total_row_idx), (-1, total_row_idx), 1, BLACK),
    ]
    # Highlight quarterly bonus rows in coral
    for idx in bonus_row_indices:
        style_cmds += [("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#FFF3F0"))]
    # Account sub-rows: subtle indented background
    for idx in acct_row_indices:
        style_cmds += [
            ("BACKGROUND",  (0, idx), (-1, idx), colors.HexColor("#F7F7F7")),
            ("FONT",        (0, idx), (-1, idx), "Helvetica", 8),
            ("TEXTCOLOR",   (0, idx), (-1, idx), DIM),
            ("LEFTPADDING", (1, idx), (1, idx),  14),
        ]

    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    return elements


# ---------------------------------------------------------------------------
# AE summary page
# ---------------------------------------------------------------------------

def _ae_summary_page(employee, period_label, summary, accelerator, currency):
    """Annual commission statement page for Account Executives."""
    elements = []
    w = CONTENT_W
    sym = _sym(currency)

    # Derive display label: period_label is e.g. "December 2026" → show "FY2026 Year-End"
    try:
        from datetime import datetime
        dt = datetime.strptime(period_label, "%B %Y")
        display_label = f"FY{dt.year} Year-End"
    except Exception:
        display_label = period_label

    elements.append(_para(f"Annual Commission Statement — {display_label}", _style(
        "ae_h1", fontName="Helvetica-Bold", fontSize=16, textColor=BLACK, spaceAfter=4
    )))
    elements.append(_para(employee.get("name", ""), _style(
        "ae_sub", fontName="Helvetica", fontSize=12, textColor=DIM, spaceAfter=10
    )))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 5*mm))

    def _fmt(v):
        if v is None or v == "" or v == 0:
            return "—"
        try:
            f = float(v)
            return f"{sym}{f:,.2f}" if f != 0 else "—"
        except Exception:
            return str(v)

    def _fmt_eur(v):
        if v is None or v == "" or v == 0:
            return "—"
        try:
            f = float(v)
            return f"€{f:,.2f}" if f != 0 else "—"
        except Exception:
            return str(v)

    def _pct(v):
        try:
            return f"{float(v):.1f}%" if v else "—"
        except Exception:
            return "—"

    # Pull values from accelerator dict (preferred) or fall back to summary
    acc = accelerator or {}
    annual_target_eur        = float(acc.get("annual_target_eur", summary.get("annual_target_eur", 0)) or 0)
    annual_acv_fy            = float(acc.get("annual_acv_first_year_eur", summary.get("acv_first_year_eur", 0)) or 0)
    annual_acv_my            = float(acc.get("annual_acv_multi_year_eur", summary.get("acv_multi_year_eur", 0)) or 0)
    annual_attainment_pct    = float(acc.get("annual_attainment_pct", 0) or 0)
    qualifying_acv_eur       = float(acc.get("qualifying_acv_eur", 0) or 0)
    base_commission          = float(acc.get("base_commission", 0) or 0)
    multi_year_commission    = float(acc.get("multi_year_commission", 0) or 0)
    accelerator_1            = float(acc.get("accelerator_1", 0) or 0)
    accelerator_2            = float(acc.get("accelerator_2", 0) or 0)
    total_commission         = float(acc.get("accelerator_topup", summary.get("accelerator_topup", summary.get("total_commission", 0))) or 0)
    q_gate_results           = acc.get("q_gate_results", {})

    rows: list[list] = [["Component", "Amount (EUR)", f"Amount ({currency})"]]
    fx = float(acc.get("fx_rate", summary.get("fx_rate", 1)) or 1)

    rows.append(["Annual Target", _fmt_eur(annual_target_eur), "—"])
    rows.append(["Total Annual ACV (1st year)", _fmt_eur(annual_acv_fy), "—"])
    rows.append(["Annual Attainment", _pct(annual_attainment_pct), "—"])

    # Q1–Q4 gate status
    for q in range(1, 5):
        gate = q_gate_results.get(q)
        if gate is not None:
            gate_str = "✓ Met" if gate else "✗ Not Met"
            rows.append([f"Q{q} Gate (≥ 50% of quarterly target)", gate_str, ""])

    rows.append(["Qualifying ACV (gate-passed quarters)", _fmt_eur(qualifying_acv_eur), "—"])
    rows.append(["Base Commission (10%)", _fmt_eur(base_commission / fx if fx else 0), _fmt(base_commission)])
    rows.append(["Multi-year ACV Commission (1%)", _fmt_eur(multi_year_commission / fx if fx else 0), _fmt(multi_year_commission)])
    rows.append(["Annual Accelerator Tier 1 (12%, 100–150% of target)", _fmt_eur(accelerator_1 / fx if fx else 0), _fmt(accelerator_1)])
    rows.append(["Annual Accelerator Tier 2 (15%, >150% of target)", _fmt_eur(accelerator_2 / fx if fx else 0), _fmt(accelerator_2)])
    rows.append(["TOTAL COMMISSION", _fmt_eur(total_commission / fx if fx else 0), _fmt(total_commission)])

    total_row_idx = len(rows) - 1

    col_w = [w - 50*mm - 50*mm, 50*mm, 50*mm]
    tbl = Table(rows, colWidths=col_w)

    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), CORAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONT",          (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("ALIGN",         (1, 0), (-1, 0), "RIGHT"),
        ("FONT",          (0, 1), (-1, total_row_idx - 1), "Helvetica", 10),
        ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, BORDER),
        *[("BACKGROUND", (0, i), (-1, i), CARD_BG) for i in range(1, total_row_idx) if i % 2 == 0],
        ("BACKGROUND",    (0, total_row_idx), (-1, total_row_idx), colors.HexColor("#EEEEEE")),
        ("FONT",          (0, total_row_idx), (-1, total_row_idx), "Helvetica-Bold", 11),
        ("LINEABOVE",     (0, total_row_idx), (-1, total_row_idx), 1.5, BLACK),
    ]
    # Colour gate rows
    for i, row in enumerate(rows[1:], start=1):
        if len(row) > 1 and isinstance(row[1], str) and "✓" in row[1]:
            style_cmds += [("TEXTCOLOR", (1, i), (1, i), GREEN)]
        elif len(row) > 1 and isinstance(row[1], str) and "✗" in row[1]:
            style_cmds += [("TEXTCOLOR", (1, i), (1, i), RED)]

    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    elements.append(Spacer(1, 6*mm))

    elements.append(_para(
        "Annual commission paid in December payroll.",
        _style("ae_note", fontName="Helvetica", fontSize=10, textColor=DIM)
    ))
    elements.append(Spacer(1, 4*mm))
    elements.append(_para(
        "Payment is made on the last payroll date of the month following the month in which "
        "the payout becomes due. Subject to statutory deductions. Confidential.",
        _style("ae_disc", fontName="Helvetica", fontSize=8, textColor=DIM)
    ))
    return elements


# ---------------------------------------------------------------------------
# AE workings page
# ---------------------------------------------------------------------------

def _ae_workings_page(employee, period_label, rows, accelerator, currency):
    """Deal-level workings for Account Executives."""
    elements = []
    w = CONTENT_W
    sym = _sym(currency)

    # Derive display year label
    try:
        from datetime import datetime
        dt = datetime.strptime(period_label, "%B %Y")
        display_label = f"FY{dt.year} Year-End"
    except Exception:
        display_label = period_label

    elements.append(_para(f"Deal Workings — {display_label}", _style(
        "ae_wk_h1", fontName="Helvetica-Bold", fontSize=14, textColor=BLACK, spaceAfter=4
    )))
    elements.append(_para(employee.get("name", ""), _style(
        "ae_wk_sub", fontName="Helvetica", fontSize=11, textColor=DIM, spaceAfter=8
    )))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 4*mm))

    if not rows:
        elements.append(_para("No qualifying deals this period.", _style(
            "ae_wk_empty", fontName="Helvetica", fontSize=10, textColor=DIM
        )))
        return elements

    # Column widths: Date | Opportunity | 1st-yr ACV (EUR) | Multi-yr ACV (EUR) | FX | Base Comm | Multi-yr Comm | Total
    col_w = [22*mm, 75*mm, 28*mm, 28*mm, 20*mm, 28*mm, 28*mm, 28*mm]
    header = ["Date", "Opportunity", "1st-yr ACV (EUR)", "Multi-yr ACV (EUR)",
              "FX Rate", "Base Comm", "Multi-yr Comm", f"Total ({currency})"]
    data = [header]

    _cell_style = ParagraphStyle("ae_wk_cell", fontName="Helvetica",  fontSize=9, leading=11)
    _fcst_style = ParagraphStyle("ae_wk_fcst", fontName="Helvetica",  fontSize=9, leading=11, textColor=DIM)

    total_base = 0.0
    total_my   = 0.0
    fcst_indices = []

    for i, r in enumerate(rows, start=1):
        is_forecast = bool(r.get("is_forecast", False))
        acv_fy  = float(r.get("acv_eur", 0))
        acv_my  = float(r.get("multi_year_acv_eur", 0))
        fx      = float(r.get("fx_rate", 1) or 1)
        base_c  = float(r.get("base_commission", 0))
        my_c    = float(r.get("my_commission", 0))
        total_c = base_c + my_c

        if not is_forecast:
            total_base += base_c
            total_my   += my_c

        date_str = r.get("date", "")
        opp_name = r.get("opportunity_name") or r.get("opportunity_id", "")
        cell_s   = _fcst_style if is_forecast else _cell_style

        total_str = f"{sym}{total_c:,.2f}"
        if is_forecast:
            total_str += " (fcst)"
            fcst_indices.append(i)

        data.append([
            date_str,
            Paragraph(str(opp_name), cell_s),
            f"€{acv_fy:,.2f}",
            f"€{acv_my:,.2f}" if acv_my else "—",
            f"{fx:.4f}",
            f"{sym}{base_c:,.2f}",
            f"{sym}{my_c:,.2f}" if my_c else "—",
            total_str,
        ])

    grand_total = total_base + total_my
    data.append(["", "", "", "", "", "", "TOTAL", f"{sym}{grand_total:,.2f}"])
    total_row_idx = len(data) - 1

    tbl = Table(data, colWidths=col_w)
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), CORAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONT",          (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT",          (0, 1), (-1, total_row_idx - 1), "Helvetica", 9),
        ("ALIGN",         (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN",         (6, total_row_idx), (6, total_row_idx), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (7, 0), (7, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        *[("BACKGROUND", (0, i), (-1, i), CARD_BG) for i in range(1, total_row_idx) if i % 2 == 0],
        ("BACKGROUND",    (0, total_row_idx), (-1, total_row_idx), colors.HexColor("#EEEEEE")),
        ("FONT",          (0, total_row_idx), (-1, total_row_idx), "Helvetica-Bold", 9),
        ("LINEABOVE",     (0, total_row_idx), (-1, total_row_idx), 1, BLACK),
    ]
    # Dim forecast rows
    for idx in fcst_indices:
        style_cmds += [("TEXTCOLOR", (0, idx), (-1, idx), DIM)]

    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    return elements


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _para(text, style):
    return Paragraph(str(text), style)


def _style(name, **kwargs):
    return ParagraphStyle(name, **kwargs)


def _sym(currency):
    return {"SEK": "kr ", "GBP": "£", "EUR": "€", "USD": "$"}.get(currency, "")


def _num(v):
    try:
        return f"{float(v):,.2f}"
    except Exception:
        return str(v)


def _rate_label(currency, kind):
    from src.commission_plans.sdr import FIXED_RATES
    rates = FIXED_RATES.get(currency, FIXED_RATES["EUR"])
    key = "outbound_sao" if kind == "outbound" else "inbound_sao"
    sym = _sym(currency)
    return f"{sym}{rates[key]:,} / SAO"


def _accel_desc(accelerator, currency):
    if not accelerator or not accelerator.get("accelerator_topup", 0):
        return "Not triggered (< 9 SAOs / quarter)"
    sym    = _sym(currency)
    excess = accelerator.get("excess_outbound", 0)
    topup  = accelerator.get("topup_per_sao", 0)
    return f"{excess} excess outbound × {sym}{topup:,} top-up"
