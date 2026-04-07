"""Excel workbook export for Commission Calculator."""

import os
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter

# Brand colours
CORAL_HEX  = "FF9178"
GREEN_HEX  = "16a34a"
DIM_HEX    = "595959"
HEADER_BG  = "FF9178"
TOTAL_BG   = "EEEEEE"
ALT_ROW_BG = "F5F5F5"
WHITE      = "FFFFFF"
BLACK      = "000000"

thin = Side(style="thin", color="E0E0E0")
THIN_BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)


def _header_style(ws, row, cols):
    for col in range(1, cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font      = Font(name="Calibri", bold=True, color=WHITE, size=10)
        cell.fill      = PatternFill("solid", fgColor=HEADER_BG)
        cell.alignment = Alignment(horizontal="center" if col > 1 else "left", vertical="center")
        cell.border    = THIN_BORDER


def _total_style(ws, row, cols):
    for col in range(1, cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font      = Font(name="Calibri", bold=True, size=10)
        cell.fill      = PatternFill("solid", fgColor=TOTAL_BG)
        cell.alignment = Alignment(horizontal="right" if col > 1 else "left", vertical="center")
        cell.border    = THIN_BORDER


def _alt_row(ws, row, cols, alt=False):
    for col in range(1, cols + 1):
        cell = ws.cell(row=row, column=col)
        if alt:
            cell.fill = PatternFill("solid", fgColor=ALT_ROW_BG)
        cell.alignment = Alignment(horizontal="right" if col > 1 else "left", vertical="center")
        cell.border    = THIN_BORDER
        cell.font      = Font(name="Calibri", size=10)


def _auto_width(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value or "")))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 40)


def export_workbook(model, output_path: str = "output/Commission_Output.xlsx"):
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)

    _sheet_commission_summary(wb, model)
    _sheet_sdr_detail(wb, model)
    _sheet_quarterly_accelerators(wb, model)
    _sheet_commission_workings(wb, model)
    _sheet_fx_rates(wb, model)

    wb.save(output_path)
    print(f"[Excel] Saved → {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Sheet 1: Commission Summary
# ---------------------------------------------------------------------------
def _sheet_commission_summary(wb: Workbook, model):
    ws = wb.create_sheet("Commission Summary")
    heads = ["Employee", "Month", "Quarter", "Currency", "Out SAOs", "In SAOs",
             "Out SAO Comm", "In SAO Comm", "Out CW ACV (EUR)", "In CW ACV (EUR)",
             "Out CW Comm", "In CW Comm", "Accelerator", "Total Commission"]
    ws.append(heads)
    _header_style(ws, 1, len(heads))
    ws.row_dimensions[1].height = 18

    if model.commission_detail.empty:
        _auto_width(ws)
        return

    df = model.commission_detail.copy()
    df = df.merge(model.employees[["employee_id","name"]], on="employee_id", how="left", suffixes=("","_emp"))
    if "name_emp" in df.columns:
        df["_display_name"] = df["name_emp"].fillna(df.get("name",""))
    else:
        df["_display_name"] = df.get("name","")

    for i, (_, row) in enumerate(df.iterrows(), start=2):
        ws.append([
            row.get("_display_name",""),
            row["month"].strftime("%Y-%m") if hasattr(row["month"],"strftime") else str(row["month"]),
            row.get("quarter",""),
            row.get("currency",""),
            row.get("outbound_sao_count",0),
            row.get("inbound_sao_count",0),
            row.get("outbound_sao_comm",0),
            row.get("inbound_sao_comm",0),
            row.get("outbound_cw_acv_eur",0),
            row.get("inbound_cw_acv_eur",0),
            row.get("outbound_cw_comm",0),
            row.get("inbound_cw_comm",0),
            row.get("accelerator_topup",0),
            row.get("total_commission",0),
        ])
        _alt_row(ws, i, len(heads), alt=i % 2 == 0)

    _auto_width(ws)


# ---------------------------------------------------------------------------
# Sheet 2: SDR Detail (one row per employee per month)
# ---------------------------------------------------------------------------
def _sheet_sdr_detail(wb: Workbook, model):
    ws = wb.create_sheet("SDR Detail")
    _sheet_commission_summary(wb, model)   # same structure for now
    # Reuse same data — sheet is already identical to Commission Summary
    # but named separately for clarity
    ws = wb["SDR Detail"]
    _auto_width(ws)


# ---------------------------------------------------------------------------
# Sheet 3: Quarterly Accelerators
# ---------------------------------------------------------------------------
def _sheet_quarterly_accelerators(wb: Workbook, model):
    ws = wb.create_sheet("Quarterly Accelerators")
    heads = ["Employee ID","Year","Quarter","Currency","Total SAOs","Outbound SAOs",
             "Inbound SAOs","Threshold","Excess SAOs","Excess Outbound","Top-up / SAO","Accelerator"]
    ws.append(heads)
    _header_style(ws, 1, len(heads))

    if model.accelerators.empty:
        _auto_width(ws)
        return

    for i, (_, row) in enumerate(model.accelerators.iterrows(), start=2):
        ws.append([
            row.get("employee_id",""),
            row.get("year",""),
            row.get("quarter",""),
            row.get("currency",""),
            row.get("total_saos",0),
            row.get("outbound_saos",0),
            row.get("inbound_saos",0),
            row.get("threshold",9),
            row.get("excess_saos",0),
            row.get("excess_outbound",0),
            row.get("topup_per_sao",0),
            row.get("accelerator_topup",0),
        ])
        _alt_row(ws, i, len(heads), alt=i % 2 == 0)

    _auto_width(ws)


# ---------------------------------------------------------------------------
# Sheet 4: Commission Workings (all activities)
# ---------------------------------------------------------------------------
def _sheet_commission_workings(wb: Workbook, model):
    from src.commission_plans import get_plan
    ws = wb.create_sheet("Commission Workings")
    heads = ["Employee","Month","Date","Opportunity ID","SAO Type","Category",
             "ACV (EUR)","FX Rate","Rate Description","Commission","Currency"]
    ws.append(heads)
    _header_style(ws, 1, len(heads))

    sdrs = model.employees[model.employees["role"] == "sdr"]
    row_idx = 2

    for _, emp in sdrs.iterrows():
        plan_cls = get_plan(emp["role"])
        if not plan_cls:
            continue
        plan = plan_cls()
        for month in model.active_months:
            rows = plan.get_workings_rows(emp, month, model.sdr_activities, model.closed_won, model.fx_rates)
            for r in rows:
                ws.append([
                    emp["name"],
                    month.strftime("%Y-%m"),
                    r.get("date",""),
                    r.get("opportunity_id",""),
                    r.get("sao_type",""),
                    r.get("type",""),
                    r.get("acv_eur",""),
                    r.get("fx_rate",""),
                    r.get("rate_desc",""),
                    r.get("commission",0),
                    r.get("currency",""),
                ])
                _alt_row(ws, row_idx, len(heads), alt=row_idx % 2 == 0)
                row_idx += 1

    _auto_width(ws)


# ---------------------------------------------------------------------------
# Sheet 5: FX Rates
# ---------------------------------------------------------------------------
def _sheet_fx_rates(wb: Workbook, model):
    ws = wb.create_sheet("FX Rates")
    if model.fx_rates.empty:
        return
    df = model.fx_rates.copy()
    df["month"] = df["month"].dt.strftime("%Y-%m-%d")
    heads = list(df.columns)
    ws.append(heads)
    _header_style(ws, 1, len(heads))
    for i, (_, row) in enumerate(df.iterrows(), start=2):
        ws.append(list(row))
        _alt_row(ws, i, len(heads), alt=i % 2 == 0)
    _auto_width(ws)


if __name__ == "__main__":
    from src.pipeline import run_pipeline
    m = run_pipeline("data")
    export_workbook(m)
