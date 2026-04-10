"""SDR commission report builders."""
import pandas as pd
from src.helpers import df_to_records, quarter_months


# ---------------------------------------------------------------------------
# Team overview: all SDRs for a given month
# ---------------------------------------------------------------------------

def team_overview(model, month: pd.Timestamp) -> dict:
    if model.commission_detail.empty:
        return {"employees": [], "kpis": {}}

    df = model.commission_detail[
        (model.commission_detail["month"] == month) &
        (model.commission_detail["role"].isin(["sdr", "sdr_lead"]))
    ].copy()

    # EUR conversion: total_commission is in local currency; fx_rate is EUR->local
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
            "role":            row.get("role", ""),
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
            # CS / CS Lead specific fields (0 for non-CS roles)
            "nrr_pct":                   r.get("nrr_pct", 0),
            "nrr_bonus":                 r.get("nrr_bonus", 0),
            "csat_score_pct":            r.get("csat_score_pct", 0),
            "csat_bonus":                r.get("csat_bonus", 0),
            "credits_used_pct":          r.get("credits_used_pct", 0),
            "credits_bonus":             r.get("credits_bonus", 0),
            "multi_year_comm":           r.get("multi_year_comm", 0),
            "referral_sao_count":        r.get("referral_sao_count", 0),
            "referral_sao_comm":         r.get("referral_sao_comm", 0),
            "referral_cw_comm":          r.get("referral_cw_comm", 0),
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
            "role":                 grp["role"].iloc[0] if "role" in grp.columns else "",
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
