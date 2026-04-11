"""SE (Solutions Engineer) commission summary and workings PDF pages."""
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable

from src.pdf._constants import CONTENT_W, CORAL, WHITE, BLACK, DIM, BORDER, CARD_BG
from src.pdf._helpers import _para, _style, _sym, _num


# ---------------------------------------------------------------------------
# SE summary page
# ---------------------------------------------------------------------------

def _se_summary_page(employee, period_label, summary, currency):
    elements = []
    w   = CONTENT_W
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

    def _tier_label(pct: float) -> str:
        if pct >= 110:
            return "> 110% \u2192 125% payout"
        if pct >= 100:
            return "100\u2013110% \u2192 100% payout"
        if pct >= 85:
            return "85\u201399.99% \u2192 90% payout"
        if pct >= 70:
            return "70\u201384.99% \u2192 75% payout"
        if pct >= 50:
            return "50\u201369.99% \u2192 50% payout"
        return "< 50% \u2192 0% payout"

    q_target   = float(summary.get("quarterly_bonus_target", 0) or 0)
    nb_pct     = float(summary.get("nb_achievement_pct",  0) or 0)
    nb_bonus   = float(summary.get("nb_bonus",            0) or 0)
    arr_pct    = float(summary.get("arr_achievement_pct", 0) or 0)
    arr_bonus  = float(summary.get("arr_bonus",           0) or 0)
    total      = float(summary.get("total_commission",    0) or 0)

    is_q_end = q_target > 0

    rows: list[list] = [["Component", "Achievement", "Tier / Rate", f"Amount ({currency})"]]

    if is_q_end:
        rows.append(["Quarterly Bonus Target", "\u2014",
                     "20% \u00d7 annual salary \u00f7 4", _fmt(q_target)])
        rows.append(["Global New Business ACV (80%)", _pct(nb_pct),
                     _tier_label(nb_pct), _fmt(nb_bonus)])
        rows.append(["Company Closing ARR (20%)", _pct(arr_pct),
                     _tier_label(arr_pct), _fmt(arr_bonus)])

    rows.append(["TOTAL PAYOUT", "", "", _fmt(total)])
    total_row_idx = len(rows) - 1

    col_w = [100*mm, 30*mm, w - 100*mm - 30*mm - 40*mm, 40*mm]
    tbl   = Table(rows, colWidths=col_w)

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
    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    elements.append(Spacer(1, 6*mm))

    if not is_q_end:
        elements.append(_para(
            "Quarterly bonus (New Business & ARR) is paid in quarter-end months only "
            "(March, June, September, December).",
            _style("note", fontName="Helvetica", fontSize=10, textColor=DIM)
        ))
        elements.append(Spacer(1, 4*mm))

    elements.append(_para(
        "Payment is made on the last payroll date of the month following the quarter end. "
        "Subject to statutory deductions. Confidential.",
        _style("disc", fontName="Helvetica", fontSize=8, textColor=DIM)
    ))
    return elements


# ---------------------------------------------------------------------------
# SE workings page
# ---------------------------------------------------------------------------

def _se_workings_page(employee, period_label, rows, summary, currency):
    elements = []
    w   = CONTENT_W
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
        "SE Bonus \u2014 New Business (80%)": float(summary.get("nb_bonus", 0) or 0),
        "SE Bonus \u2014 Company ARR (20%)":  float(summary.get("arr_bonus", 0) or 0),
    }

    col_w  = [22*mm, 62*mm, 75*mm, w - 22*mm - 62*mm - 75*mm - 36*mm, 36*mm]
    header = ["Date", "Component", "Period / Label", "Rate / Tier", f"Amount ({currency})"]
    data   = [header]

    _cell_style    = ParagraphStyle("se_wk_cell",  fontName="Helvetica",      fontSize=9, leading=11)
    _bonus_style   = ParagraphStyle("se_wk_bonus", fontName="Helvetica-Bold", fontSize=9, leading=11,
                                    textColor=CORAL)
    _info_style    = ParagraphStyle("se_wk_info",  fontName="Helvetica",      fontSize=8, leading=10,
                                    textColor=DIM)
    _section_style = ParagraphStyle("se_wk_sect",  fontName="Helvetica-Bold", fontSize=9, leading=11,
                                    textColor=WHITE)

    total = 0.0
    bonus_row_indices   = []
    section_row_indices = []
    info_row_indices    = []

    for i, r in enumerate(rows, start=1):
        row_type = r.get("type", "")
        account  = r.get("opportunity_name") or r.get("opportunity_id", "")
        rate_desc = r.get("rate_desc", "") or ""

        is_bonus   = row_type in _bonus_amts
        is_section = row_type == "CS Section"
        is_info    = row_type in ("SE NB Actuals", "SE ARR Actuals")

        if is_section:
            data.append([Paragraph(str(account), _section_style), "", "", "", ""])
            section_row_indices.append(i)
        elif is_info:
            data.append([
                "",
                Paragraph(row_type, _info_style),
                Paragraph(str(account), _info_style),
                Paragraph(rate_desc, _info_style),
                "\u2014",
            ])
            info_row_indices.append(i)
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
    for idx in bonus_row_indices:
        style_cmds += [("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#FFF3F0"))]

    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    return elements
