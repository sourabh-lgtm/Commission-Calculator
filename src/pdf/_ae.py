"""AE annual commission summary and workings PDF pages."""
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable

from src.pdf._constants import CONTENT_W, CORAL, WHITE, BLACK, DIM, BORDER, CARD_BG, GREEN, RED
from src.pdf._helpers import _para, _style, _sym


# ---------------------------------------------------------------------------
# AE summary page
# ---------------------------------------------------------------------------

def _ae_summary_page(employee, period_label, summary, accelerator, currency):
    """Annual commission statement page for Account Executives."""
    elements = []
    w = CONTENT_W
    sym = _sym(currency)

    # Derive display label: period_label is e.g. "December 2026" -> show "FY2026 Year-End"
    try:
        dt = datetime.strptime(period_label, "%B %Y")
        display_label = f"FY{dt.year} Year-End"
    except Exception:
        display_label = period_label

    elements.append(_para(f"Annual Commission Statement \u2014 {display_label}", _style(
        "ae_h1", fontName="Helvetica-Bold", fontSize=16, textColor=BLACK, spaceAfter=4
    )))
    elements.append(_para(employee.get("name", ""), _style(
        "ae_sub", fontName="Helvetica", fontSize=12, textColor=DIM, spaceAfter=10
    )))
    elements.append(HRFlowable(width=w, color=BORDER, thickness=1))
    elements.append(Spacer(1, 5*mm))

    def _fmt(v):
        if v is None or v == "" or v == 0:
            return "\u2014"
        try:
            f = float(v)
            return f"{sym}{f:,.2f}" if f != 0 else "\u2014"
        except Exception:
            return str(v)

    def _fmt_eur(v):
        if v is None or v == "" or v == 0:
            return "\u2014"
        try:
            f = float(v)
            return f"\u20ac{f:,.2f}" if f != 0 else "\u2014"
        except Exception:
            return str(v)

    def _pct(v):
        try:
            return f"{float(v):.1f}%" if v else "\u2014"
        except Exception:
            return "\u2014"

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
    ramp_passed              = acc.get("ramp_passed")          # True / False / None
    ramp_bonus               = float(acc.get("ramp_bonus", 0) or 0)

    rows: list[list] = [["Component", "Amount (EUR)", f"Amount ({currency})"]]
    fx = float(acc.get("fx_rate", summary.get("fx_rate", 1)) or 1)

    rows.append(["Annual Target", _fmt_eur(annual_target_eur), "\u2014"])
    rows.append(["Total Annual ACV (1st year)", _fmt_eur(annual_acv_fy), "\u2014"])
    rows.append(["Annual Attainment", _pct(annual_attainment_pct), "\u2014"])

    # Q1-Q4 gate status
    for q in range(1, 5):
        gate = q_gate_results.get(q)
        if gate is not None:
            gate_str = "\u2713 Met" if gate else "\u2717 Not Met"
            rows.append([f"Q{q} Gate (\u2265 50% of quarterly target)", gate_str, ""])

    # Ramp period section (Q1 only, for employees on ramp plan)
    if ramp_passed is not None:
        ramp_criteria_str = "\u2713 All criteria met" if ramp_passed else "\u2717 Criteria not met"
        rows.append(["Q1 Ramp Period (01/01/2026\u201331/03/2026)", ramp_criteria_str, ""])
        if ramp_bonus > 0:
            rows.append([
                "  Q1 Ramp Bonus (50% of quarterly OTE: pipeline \u2265\u20ac200k, 7+ sol.design opps, \u226550% self-gen)",
                _fmt_eur(ramp_bonus / fx if fx else 0),
                _fmt(ramp_bonus),
            ])

    rows.append(["Qualifying ACV (gate-passed quarters)", _fmt_eur(qualifying_acv_eur), "\u2014"])
    rows.append(["Base Commission (10%)", _fmt_eur(base_commission / fx if fx else 0), _fmt(base_commission)])
    rows.append(["Multi-year ACV Commission (1%)", _fmt_eur(multi_year_commission / fx if fx else 0), _fmt(multi_year_commission)])
    rows.append(["Annual Accelerator Tier 1 (12%, 100\u2013150% of target)", _fmt_eur(accelerator_1 / fx if fx else 0), _fmt(accelerator_1)])
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
        if len(row) > 1 and isinstance(row[1], str) and "\u2713" in row[1]:
            style_cmds += [("TEXTCOLOR", (1, i), (1, i), GREEN)]
        elif len(row) > 1 and isinstance(row[1], str) and "\u2717" in row[1]:
            style_cmds += [("TEXTCOLOR", (1, i), (1, i), RED)]

    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    elements.append(Spacer(1, 6*mm))

    q_month_names = {1: "March", 2: "June", 3: "September", 4: "December"}
    final_q = int(acc.get("quarter", 4) or 4)
    payroll_month = q_month_names.get(final_q, "December")
    elements.append(_para(
        f"Commission paid in {payroll_month} payroll.",
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
        dt = datetime.strptime(period_label, "%B %Y")
        display_label = f"FY{dt.year} Year-End"
    except Exception:
        display_label = period_label

    elements.append(_para(f"Deal Workings \u2014 {display_label}", _style(
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
            f"\u20ac{acv_fy:,.2f}",
            f"\u20ac{acv_my:,.2f}" if acv_my else "\u2014",
            f"{fx:.4f}",
            f"{sym}{base_c:,.2f}",
            f"{sym}{my_c:,.2f}" if my_c else "\u2014",
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


