"""API report builders — called from HTTP handler in launch.py."""

import pandas as pd
from src.helpers import df_to_records, month_to_quarter, quarter_months
from src.commission_plans import get_plan


# ---------------------------------------------------------------------------
# Team overview: all SDRs for a given month
# ---------------------------------------------------------------------------

def team_overview(model, month: pd.Timestamp) -> dict:
    if model.commission_detail.empty:
        return {"employees": [], "kpis": {}}

    df = model.commission_detail[model.commission_detail["month"] == month].copy()

    # EUR conversion: total_commission is in local currency; fx_rate is EUR→local
    if not df.empty:
        df["total_commission_eur"] = df["total_commission"] / df["fx_rate"].clip(lower=1e-6)
    else:
        df["total_commission_eur"] = 0.0

    # Team-level KPIs
    total_comm_eur = float(df["total_commission_eur"].sum()) if not df.empty else 0
    total_saos   = int(df["total_sao_count"].sum())   if not df.empty and "total_sao_count" in df.columns else 0
    avg_attain   = float(df["attainment_pct"].mean())  if not df.empty and "attainment_pct" in df.columns else 0
    num_sdrs     = int(df["employee_id"].nunique())

    employees = []
    for _, row in df.iterrows():
        employees.append({
            "employee_id":     row["employee_id"],
            "name":            row["name"],
            "title":           row["title"],
            "region":          row["region"],
            "currency":        row["currency"],
            "outbound_saos":   row.get("outbound_sao_count", 0),
            "inbound_saos":    row.get("inbound_sao_count", 0),
            "total_saos":      row.get("total_sao_count", 0),
            "attainment_pct":  row.get("attainment_pct", 0),
            "outbound_cw_comm": row.get("outbound_cw_comm", 0),
            "inbound_cw_comm":  row.get("inbound_cw_comm", 0),
            "accelerator_topup": row.get("accelerator_topup", 0),
            "total_commission": row.get("total_commission", 0),
            "total_commission_eur": round(float(row["total_commission_eur"]), 2),
        })

    return {
        "employees": employees,
        "kpis": {
            "total_commission_eur": round(total_comm_eur, 2),
            "total_saos":           total_saos,
            "avg_attainment":       round(avg_attain, 1),
            "num_sdrs":             num_sdrs,
        },
    }


# ---------------------------------------------------------------------------
# SDR detail: one employee across all months (or a specific month)
# ---------------------------------------------------------------------------

def sdr_detail(model, employee_id: str, month: pd.Timestamp | None = None) -> dict:
    if model.commission_detail.empty:
        return {"rows": [], "employee": {}}

    df = model.commission_detail[model.commission_detail["employee_id"] == employee_id].copy()
    if month is not None:
        df = df[df["month"] == month]

    emp_row = model.employees[model.employees["employee_id"] == employee_id]
    employee = emp_row.iloc[0].to_dict() if not emp_row.empty else {}

    rows = []
    for _, r in df.sort_values("month").iterrows():
        rows.append({
            "month":                     r["month"].strftime("%Y-%m") if hasattr(r["month"], "strftime") else str(r["month"]),
            "quarter":                   r.get("quarter", ""),
            "outbound_saos":             r.get("outbound_sao_count", 0),
            "inbound_saos":              r.get("inbound_sao_count", 0),
            "outbound_sao_comm":         r.get("outbound_sao_comm", 0),
            "inbound_sao_comm":          r.get("inbound_sao_comm", 0),
            "outbound_cw_acv_eur":       r.get("outbound_cw_acv_eur", 0),
            "inbound_cw_acv_eur":        r.get("inbound_cw_acv_eur", 0),
            "outbound_cw_comm":          r.get("outbound_cw_comm", 0),
            "inbound_cw_comm":           r.get("inbound_cw_comm", 0),
            "outbound_cw_forecast_comm": r.get("outbound_cw_forecast_comm", 0),
            "inbound_cw_forecast_comm":  r.get("inbound_cw_forecast_comm", 0),
            "fx_rate":                   r.get("fx_rate", 1),
            "accelerator_topup":         r.get("accelerator_topup", 0),
            "spif_amount":               r.get("spif_amount", 0),
            "total_commission":          r.get("total_commission", 0),
            "attainment_pct":            r.get("attainment_pct", 0),
            "currency":                  r.get("currency", ""),
        })

    ytd_total = float(df["total_commission"].sum())
    ytd_saos  = int(df["total_sao_count"].sum()) if "total_sao_count" in df.columns else 0

    return {
        "employee": {k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in employee.items()},
        "rows": rows,
        "ytd_commission": round(ytd_total, 2),
        "ytd_saos": ytd_saos,
    }


# ---------------------------------------------------------------------------
# Monthly summary: all employees side-by-side for a month
# ---------------------------------------------------------------------------

def monthly_summary(model, month: pd.Timestamp) -> list[dict]:
    return team_overview(model, month)["employees"]


# ---------------------------------------------------------------------------
# Quarterly summary
# ---------------------------------------------------------------------------

def quarterly_summary(model, year: int, quarter: int) -> dict:
    months = quarter_months(year, quarter)

    if model.commission_detail.empty:
        return {"employees": [], "accelerators": []}

    df = model.commission_detail[model.commission_detail["month"].isin(months)].copy()

    # EUR conversion per row before grouping
    if not df.empty:
        df["total_commission_eur"] = df["total_commission"] / df["fx_rate"].clip(lower=1e-6)
    else:
        df["total_commission_eur"] = 0.0

    emp_rows = []
    for emp_id, grp in df.groupby("employee_id"):
        emp_rows.append({
            "employee_id":          emp_id,
            "name":                 grp["name"].iloc[0],
            "region":               grp["region"].iloc[0],
            "currency":             grp["currency"].iloc[0],
            "outbound_saos":        int(grp["outbound_sao_count"].sum()) if "outbound_sao_count" in grp else 0,
            "inbound_saos":         int(grp["inbound_sao_count"].sum())  if "inbound_sao_count" in grp else 0,
            "total_saos":           int(grp["total_sao_count"].sum())    if "total_sao_count" in grp else 0,
            "total_commission":     round(float(grp["total_commission"].sum()), 2),
            "total_commission_eur": round(float(grp["total_commission_eur"].sum()), 2),
            "accelerator_topup":    round(float(grp["accelerator_topup"].sum()), 2),
            "threshold":            9,
            "target_met":           int(grp["total_sao_count"].sum()) >= 9 if "total_sao_count" in grp else False,
        })

    accel_rows = []
    if not model.accelerators.empty:
        acc = model.accelerators[
            (model.accelerators["year"] == year) &
            (model.accelerators["quarter"] == quarter)
        ]
        accel_rows = df_to_records(acc)

    return {"employees": emp_rows, "accelerators": accel_rows, "year": year, "quarter": quarter}


# ---------------------------------------------------------------------------
# Commission workings: row-level audit trail
# ---------------------------------------------------------------------------

def commission_workings(model, employee_id: str, month: pd.Timestamp) -> dict:
    emp_row = model.employees[model.employees["employee_id"] == employee_id]
    if emp_row.empty:
        return {"rows": [], "summary": {}}

    emp = emp_row.iloc[0]
    plan_cls = get_plan(emp["role"])
    if plan_cls is None:
        return {"rows": [], "summary": {}}

    plan = plan_cls()
    rows = plan.get_workings_rows(
        emp, month,
        model.sdr_activities,
        model.closed_won,
        model.fx_rates,
    )

    # Append SPIF rows for this employee + month
    if not model.spif_awards.empty:
        spifs = model.spif_awards[
            (model.spif_awards["employee_id"] == employee_id) &
            (model.spif_awards["payment_month"] == month)
        ]
        for _, s in spifs.iterrows():
            rows.append({
                "type":             "SPIF",
                "date":             str(s.get("close_date", "") or ""),
                "opportunity_id":   s["spif_id"],
                "opportunity_name": s["description"],
                "document_number":  "",
                "sao_type":         "",
                "acv_eur":          None,
                "fx_rate":          None,
                "rate_desc":        "SPIF Award",
                "commission":       float(s["amount"]),
                "currency":         s["currency"],
                "is_forecast":      False,
            })

    # Summary from commission_detail
    det = model.commission_detail[
        (model.commission_detail["employee_id"] == employee_id) &
        (model.commission_detail["month"] == month)
    ]
    summary = det.iloc[0].to_dict() if not det.empty else {}
    summary = {k: (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v)
               for k, v in summary.items()}

    return {"rows": rows, "summary": summary}


# ---------------------------------------------------------------------------
# Employees list
# ---------------------------------------------------------------------------

def employee_list(model) -> list[dict]:
    sdrs = model.employees[model.employees["role"] == "sdr"].copy()
    return df_to_records(sdrs[["employee_id", "name", "title", "region", "currency"]])


# ---------------------------------------------------------------------------
# Available months
# ---------------------------------------------------------------------------

def available_months(model) -> list[str]:
    return [m.strftime("%Y-%m-%d") for m in model.active_months]
