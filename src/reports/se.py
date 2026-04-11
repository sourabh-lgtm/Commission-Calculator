"""SE (Solutions Engineer) commission report builders."""
import pandas as pd
from src.helpers import quarter_months


def se_overview(model, month: pd.Timestamp) -> dict:
    if model.commission_detail.empty:
        return {"employees": [], "kpis": {"total_bonus_eur": 0, "num_active": 0}}

    se_ids = set(model.employees[model.employees["role"] == "se"]["employee_id"])
    df = model.commission_detail[
        (model.commission_detail["month"] == month) &
        model.commission_detail["employee_id"].isin(se_ids)
    ].copy()

    if not df.empty:
        df["total_commission_eur"] = df["total_commission"] / df["fx_rate"].clip(lower=1e-6)
    else:
        df["total_commission_eur"] = 0.0

    _se_cols = ["nb_achievement_pct", "nb_bonus", "arr_achievement_pct", "arr_bonus",
                "quarterly_bonus_target"]

    employees = []
    for _, row in df.iterrows():
        emp = {
            "employee_id":          row["employee_id"],
            "name":                 row["name"],
            "title":                row["title"],
            "role":                 row.get("role", "se"),
            "region":               row["region"],
            "currency":             row["currency"],
            "total_commission":     round(float(row.get("total_commission", 0)), 2),
            "total_commission_eur": round(float(row["total_commission_eur"]), 2),
        }
        for col in _se_cols:
            emp[col] = round(float(row.get(col, 0) or 0), 2)
        employees.append(emp)

    total_eur = float(df["total_commission_eur"].sum()) if not df.empty else 0.0

    return {
        "employees": employees,
        "kpis": {
            "total_bonus_eur": round(total_eur, 2),
            "num_active":      int(df["employee_id"].nunique()) if not df.empty else 0,
        },
    }


def se_quarterly(model, year: int, quarter: int) -> dict:
    months = quarter_months(year, quarter)

    if model.commission_detail.empty:
        return {"employees": [], "year": year, "quarter": quarter}

    se_ids = set(model.employees[model.employees["role"] == "se"]["employee_id"])
    df = model.commission_detail[
        model.commission_detail["month"].isin(months) &
        model.commission_detail["employee_id"].isin(se_ids)
    ].copy()

    if df.empty:
        return {"employees": [], "year": year, "quarter": quarter}

    _sum_cols  = ["nb_bonus", "arr_bonus", "total_commission"]
    _qend_cols = ["nb_achievement_pct", "arr_achievement_pct", "quarterly_bonus_target"]
    _qend_months = {3, 6, 9, 12}

    emp_rows = []
    for emp_id, grp in df.groupby("employee_id"):
        qe = grp[grp["month"].apply(lambda m: m.month in _qend_months)]
        row = {
            "employee_id": emp_id,
            "name":        grp["name"].iloc[0],
            "role":        grp["role"].iloc[0] if "role" in grp.columns else "se",
            "region":      grp["region"].iloc[0],
            "currency":    grp["currency"].iloc[0],
        }
        for col in _sum_cols:
            row[col] = round(float(grp[col].sum()) if col in grp.columns else 0, 2)
        for col in _qend_cols:
            row[col] = round(float(qe[col].iloc[0]) if not qe.empty and col in qe.columns else 0, 2)
        emp_rows.append(row)

    return {"employees": emp_rows, "year": year, "quarter": quarter}
