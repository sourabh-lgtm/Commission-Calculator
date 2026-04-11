"""AM commission summary and workings PDF pages."""
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable

from src.pdf._constants import CONTENT_W, CORAL, WHITE, BLACK, DIM, BORDER, CARD_BG
from src.pdf._helpers import _para, _style, _sym, _num


# ---------------------------------------------------------------------------
# AM summary page
# ---------------------------------------------------------------------------

def _am_summary_page(employee, period_label, summary, currency):
    elements = []
    w = CONTENT_W
    sym = _sym(currency)

    elements.append(_para(f"Bonus Summary \u2014 {period_label}", _style(
        "h1", fontName="Helvetica-Bold", fontSize=16, textColor=BLACK, spaceAfter=4
    )))
    elements.append(_para(employee.get("name", ""), _style(
        "sub", fontName="Helvetica", fontSize=12, textColor=DIM, spaceAfter=10
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

    def _pct(v):
        try:
            return f"{float(v):.1f}%" if v else "\u2014"
        except Exception:
            return "\u2014"

    is_lead     = employee.get("role") == "am_lead"
    nrr_label   = "Team NRR (100% weight)" if is_lead else "NRR (100% weight)"

    nrr_pct         = float(summary.get("nrr_pct", 0) or 0)
    q_target        = float(summary.get("quarterly_bonus_target", 0) or 0)
    nrr_bonus       = float(summary.get("nrr_bonus", 0) or 0)
    accel_topup     = float(summary.get("accelerator_topup", 0) or 0)
    multi_year_comm = float(summary.get("multi_year_comm", 0) or 0)
    ref_sao_count   = int(summary.get("referral_sao_count", 0) or 0)
    ref_sao_comm    = float(summary.get("referral_sao_comm", 0) or 0)
    ref_cw_comm     = float(summary.get("referral_cw_comm", 0) or 0)
    total           = float(summary.get("total_commission", 0) or 0)

    # NRR tier description — approximate (actual step depends on per-employee target)
    if nrr_pct >= 100:
        nrr_tier = "\u2265 100% \u2192 100% payout"
    elif nrr_pct >= 98:
        nrr_tier = "98\u2013100% band \u2192 90% payout"
    elif nrr_pct >= 96:
        nrr_tier = "96\u201398% band \u2192 80% payout"
    elif nrr_pct >= 94:
        nrr_tier = "94\u201396% band \u2192 70% payout"
    elif nrr_pct >= 92:
        nrr_tier = "92\u201394% band \u2192 60% payout"
    elif nrr_pct >= 90:
        nrr_tier = "90\u201392% band \u2192 50% payout"
    else:
        nrr_tier = "< 90% \u2192 0%"

    is_q_end = q_target > 0

    rows: list[list] = [["Component", "Score / Qty", "Rate / Basis", f"Amount ({currency})"]]

    if is_q_end:
        rows += [
            ["Quarterly Bonus Target", "\u2014", "20% \u00d7 annual salary \u00f7 4", _fmt(q_target)],
            [nrr_label, _pct(nrr_pct), nrr_tier, _fmt(nrr_bonus)],
        ]
        if accel_topup:
            excess = round(nrr_pct - 100, 2) if nrr_pct > 100 else 0
            rows.append(["NRR Accelerator Top-up", f"+{excess:.1f}% above 100%",
                         "+2% of NRR portion per 1% above 100% (Q4 only)", _fmt(accel_topup)])

    if multi_year_comm:
        rows.append(["Multi-year ACV Commission (1%)", "\u2014",
                     "1% of year-2+ ACV on multi-year renewal deals", _fmt(multi_year_comm)])

    if ref_sao_count:
        rows.append(["Referral SAO Commissions",
                     f"{ref_sao_count} referral{'s' if ref_sao_count != 1 else ''}",
                     "Fixed rate per referral confirmed as SAO", _fmt(ref_sao_comm)])
    if ref_cw_comm:
        rows.append(["Referral Closed-Won Comm", "\u2014", "5% / 1% of ACV (outbound / inbound)",
                     _fmt(ref_cw_comm)])

    rows.append(["TOTAL PAYOUT", "", "", _fmt(total)])
    total_row_idx = len(rows) - 1

    col_w = [100*mm, 32*mm, w - 100*mm - 32*mm - 40*mm, 40*mm]
    tbl = Table(rows, colWidths=col_w)

    style_cmds = [
        ("BACKGROUND",   (0, 0), (-1, 0), CORAL),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONT",         (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("ALIGN",        (1, 0), (-1, 0), "RIGHT"),
        ("FONT",         (0, 1), (-1, total_row_idx - 1), "Helvetica", 10),
        ("ALIGN",        (1, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("GRID",         (0, 0), (-1, -1), 0.5, BORDER),
        *[("BACKGROUND", (0, i), (-1, i), CARD_BG) for i in range(1, total_row_idx) if i % 2 == 0],
        ("BACKGROUND",   (0, total_row_idx), (-1, total_row_idx), colors.HexColor("#EEEEEE")),
        ("FONT",         (0, total_row_idx), (-1, total_row_idx), "Helvetica-Bold", 11),
        ("LINEABOVE",    (0, total_row_idx), (-1, total_row_idx), 1.5, BLACK),
    ]
    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    elements.append(Spacer(1, 6*mm))

    if not is_q_end:
        elements.append(_para(
            "Quarterly bonus (NRR) is paid in quarter-end months only "
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
# AM workings page
# ---------------------------------------------------------------------------

def _am_workings_page(employee, period_label, rows, summary, currency):
    """AM workings — same structural row types as CS, different bonus type key."""
    elements = []
    w = CONTENT_W
    sym = _sym(currency)

    elements.append(_para(f"Bonus Workings \u2014 {period_label}", _style(
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

    _bonus_amts = {
        "AM Bonus \u2014 NRR (100%)": float(summary.get("nrr_bonus", 0) or 0),
    }

    col_w = [22*mm, 62*mm, 75*mm, w - 22*mm - 62*mm - 75*mm - 36*mm, 36*mm]
    header = ["Date", "Component", "Account / Period", "Rate / Tier", f"Amount ({currency})"]
    data = [header]

    _cell_style   = ParagraphStyle("am_wk_cell",  fontName="Helvetica",      fontSize=9, leading=11)
    _bonus_style  = ParagraphStyle("am_wk_bonus", fontName="Helvetica-Bold", fontSize=9, leading=11,
                                   textColor=CORAL)
    _fcst_style   = ParagraphStyle("am_wk_fcst",  fontName="Helvetica",      fontSize=9, leading=11,
                                   textColor=DIM)
    _acct_style   = ParagraphStyle("am_wk_acct",  fontName="Helvetica",      fontSize=8, leading=10,
                                   textColor=DIM)
    _acct_b_style = ParagraphStyle("am_wk_acctb", fontName="Helvetica-Bold", fontSize=8, leading=10,
                                   textColor=DIM)
    _section_style = ParagraphStyle("am_wk_sect", fontName="Helvetica-Bold", fontSize=9, leading=11,
                                    textColor=WHITE)
    _info_style    = ParagraphStyle("am_wk_info",  fontName="Helvetica",      fontSize=8, leading=10,
                                    textColor=DIM)

    total = 0.0
    bonus_row_indices   = []
    acct_row_indices    = []
    section_row_indices = []
    info_row_indices    = []
    num_border_indices  = []

    for i, r in enumerate(rows, start=1):
        row_type    = r.get("type", "")
        is_bonus    = row_type in _bonus_amts
        is_forecast = bool(r.get("is_forecast", False))
        is_acct     = row_type == "CS NRR Account"
        is_section  = row_type == "CS Section"
        is_nrr_bob  = row_type == "CS NRR BoB"
        is_nrr_num  = row_type == "CS NRR Numerator"
        is_cred_det = row_type == "CS Credits Detail"

        account   = r.get("opportunity_name") or r.get("opportunity_id", "")
        rate_desc = r.get("rate_desc", "") or ""

        if r.get("acv_eur") and r.get("fx_rate"):
            rate_desc = (f"ACV {_sym('EUR')}{_num(r['acv_eur'])} EUR "
                         f"\u00d7 {float(r['fx_rate']):.4f} \u2192 {rate_desc}")

        if is_section:
            data.append([Paragraph(str(account), _section_style), "", "", "", ""])
            section_row_indices.append(i)
        elif is_nrr_bob or is_nrr_num:
            comm_val = r.get("commission")
            amt_str  = f"{int(comm_val):,}" if comm_val is not None else "\u2014"
            label    = "Base BoB" if is_nrr_bob else "NRR Numerator"
            data.append([
                "",
                Paragraph(label, _info_style),
                Paragraph(str(account), _info_style),
                Paragraph(rate_desc, _info_style),
                amt_str,
            ])
            info_row_indices.append(i)
            if is_nrr_num:
                num_border_indices.append(i)
        elif is_acct or is_cred_det:
            comm_val = r.get("commission")
            comm_str = f"{comm_val:+,.0f}" if (is_acct and comm_val) else "\u2014"
            data.append([
                "",
                Paragraph("  \u21b3", _acct_style),
                Paragraph(str(account), _acct_b_style),
                Paragraph(rate_desc, _acct_style),
                comm_str,
            ])
            acct_row_indices.append(i)
        elif is_bonus:
            comm = _bonus_amts.get(row_type, 0.0)
            total += comm
            comm_str = f"{sym}{comm:,.2f}" if comm else "\u2014"
            data.append([
                r.get("date", ""),
                Paragraph(row_type, _bonus_style),
                Paragraph(str(account), _cell_style),
                Paragraph(rate_desc, _cell_style),
                comm_str,
            ])
            bonus_row_indices.append(i)
        elif is_forecast:
            comm = float(r.get("commission") or 0)
            data.append([
                r.get("date", ""),
                Paragraph(row_type, _fcst_style),
                Paragraph(str(account), _cell_style),
                Paragraph(rate_desc, _cell_style),
                f"{sym}{comm:,.2f} (forecast)",
            ])
        else:
            comm = float(r.get("commission") or 0)
            total += comm
            data.append([
                r.get("date", ""),
                Paragraph(row_type, _cell_style),
                Paragraph(str(account), _cell_style),
                Paragraph(rate_desc, _cell_style),
                f"{sym}{comm:,.2f}",
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
    for idx in section_row_indices:
        style_cmds += [
            ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#3f3f3f")),
            ("TEXTCOLOR",  (0, idx), (-1, idx), WHITE),
            ("FONT",       (0, idx), (-1, idx), "Helvetica-Bold", 9),
            ("SPAN",       (0, idx), (-1, idx)),
            ("LINEABOVE",  (0, idx), (-1, idx), 1, colors.HexColor("#555555")),
        ]
    for idx in info_row_indices:
        style_cmds += [
            ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#F9FAFB")),
            ("TEXTCOLOR",  (0, idx), (-1, idx), DIM),
            ("FONT",       (0, idx), (-1, idx), "Helvetica", 8),
        ]
    for idx in num_border_indices:
        style_cmds += [("LINEBELOW", (0, idx), (-1, idx), 1, BORDER)]
    for idx in bonus_row_indices:
        style_cmds += [("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#FFF3F0"))]
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
