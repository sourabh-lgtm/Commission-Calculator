"""API report builders — called from HTTP handler in launch.py."""

import pandas as pd
from src.helpers import df_to_records, month_to_quarter, quarter_months, get_fx_rate
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
    cs_perf = getattr(model, "cs_performance", None)
    if emp["role"] == "cs" and cs_perf:
        rows = plan.get_workings_rows(
            emp, month,
            model.sdr_activities,
            model.closed_won,
            model.fx_rates,
            cs_performance=cs_perf,
        )
    elif emp["role"] == "ae" and cs_perf:
        rows = plan.get_workings_rows(
            emp, month,
            model.sdr_activities,
            model.closed_won,
            model.fx_rates,
            cs_performance=cs_perf,
        )
    else:
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
# Payroll summary: per-employee monthly commission (for payroll team)
# ---------------------------------------------------------------------------

def payroll_summary(model, year: int) -> dict:
    all_months  = sorted(model.active_months)
    year_months = [m for m in all_months if m.year == year]
    if not year_months:
        return {"months": [], "month_labels": [], "regions": []}

    df = model.commission_detail[model.commission_detail["month"].isin(year_months)].copy()
    month_keys   = [m.strftime("%Y-%m") for m in year_months]
    month_labels = [m.strftime("%b-%y") for m in year_months]

    def _q(m): return (m.month - 1) // 3 + 1

    commissioned = model.employees[
        model.employees["role"].isin(["sdr", "cs", "cs_lead", "ae"])
    ].copy()
    regions: dict[str, list] = {}

    for _, emp in commissioned.iterrows():
        emp_id = emp["employee_id"]
        region = emp["region"]
        edf    = df[df["employee_id"] == emp_id]
        monthly = {}
        for m in year_months:
            mrow = edf[edf["month"] == m]
            monthly[m.strftime("%Y-%m")] = round(float(mrow["total_commission"].iloc[0]), 2) if not mrow.empty else 0.0
        q_totals = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        for m in year_months:
            q_totals[_q(m)] += monthly[m.strftime("%Y-%m")]
        q_totals = {k: round(v, 2) for k, v in q_totals.items()}
        regions.setdefault(region, []).append({
            "employee_id":      str(emp_id),
            "name":             emp["name"],
            "cost_center_code": emp.get("cost_center_code", ""),
            "currency":         emp["currency"],
            "monthly":          monthly,
            "q1": q_totals[1], "q2": q_totals[2],
            "q3": q_totals[3], "q4": q_totals[4],
            "total":            round(sum(monthly.values()), 2),
        })

    return {
        "months":       month_keys,
        "month_labels": month_labels,
        "regions":      [{"region": r, "employees": emps} for r, emps in regions.items()],
    }


# ---------------------------------------------------------------------------
# Accrual summary: department-level EUR totals (for finance)
# ---------------------------------------------------------------------------

def accrual_summary(model, year: int) -> dict:
    all_months  = sorted(model.active_months)
    year_months = [m for m in all_months if m.year == year]
    if not year_months:
        return {"months": [], "month_labels": [], "regions": []}

    df = model.commission_detail[model.commission_detail["month"].isin(year_months)].copy()
    month_keys   = [m.strftime("%Y-%m") for m in year_months]
    month_labels = [m.strftime("%b-%y") for m in year_months]

    def _q(m): return (m.month - 1) // 3 + 1

    regions: dict[str, list] = {}

    # ---- SDR employees: accrual = actual commission ----
    sdrs = model.employees[model.employees["role"] == "sdr"].copy()
    for _, emp in sdrs.iterrows():
        emp_id   = emp["employee_id"]
        region   = emp["region"]
        currency = emp["currency"]
        edf      = df[df["employee_id"] == emp_id]
        monthly  = {}
        for m in year_months:
            mg = edf[edf["month"] == m]
            monthly[m.strftime("%Y-%m")] = round(float(mg["total_commission"].sum()), 2)
        q_totals = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        for m in year_months:
            q_totals[_q(m)] += monthly[m.strftime("%Y-%m")]
        q_totals = {k: round(v, 2) for k, v in q_totals.items()}
        total = round(sum(monthly.values()), 2)

        base = {
            "employee_id":      str(emp_id),
            "name":             emp["name"],
            "cost_center_code": emp.get("cost_center_code", ""),
            "currency":         currency,
            "monthly":          monthly,
            "q1": q_totals[1], "q2": q_totals[2],
            "q3": q_totals[3], "q4": q_totals[4],
            "total":            total,
        }
        regions.setdefault(region, []).append({**base, "type": "Commission"})

        if region == "UK":
            ni_monthly = {k: round(v * 0.138, 2) for k, v in monthly.items()}
            ni_q       = {k: round(v * 0.138, 2) for k, v in q_totals.items()}
            regions[region].append({
                **base,
                "type":    "Employer NI (13.8%)",
                "monthly": ni_monthly,
                "q1": ni_q[1], "q2": ni_q[2],
                "q3": ni_q[3], "q4": ni_q[4],
                "total":   round(total * 0.138, 2),
            })
        if region == "Nordics":
            sc_monthly = {k: round(v * 0.31, 2) for k, v in monthly.items()}
            sc_q       = {k: round(v * 0.31, 2) for k, v in q_totals.items()}
            regions[region].append({
                **base,
                "type":    "Employer Social Contributions (31%)",
                "monthly": sc_monthly,
                "q1": sc_q[1], "q2": sc_q[2],
                "q3": sc_q[3], "q4": sc_q[4],
                "total":   round(total * 0.31, 2),
            })

    # ---- CS employees: accrual = full potential (salary × 15%), not actual bonus ----
    cs_employees = model.employees[model.employees["role"] == "cs"].copy()
    for _, emp in cs_employees.iterrows():
        emp_id   = emp["employee_id"]
        region   = emp["region"]
        currency = emp["currency"]
        sal_hist = model.salary_history[model.salary_history["employee_id"] == emp_id]

        monthly = {}
        for m in year_months:
            eligible = (
                sal_hist[sal_hist["effective_date"] <= m]
                .sort_values("effective_date", ascending=False)
            )
            sal_monthly = float(eligible["salary_monthly"].iloc[0]) if not eligible.empty else 0.0
            monthly[m.strftime("%Y-%m")] = round(sal_monthly * 0.15, 2)

        q_totals = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        for m in year_months:
            q_totals[_q(m)] += monthly[m.strftime("%Y-%m")]
        q_totals = {k: round(v, 2) for k, v in q_totals.items()}
        total = round(sum(monthly.values()), 2)

        base = {
            "employee_id":      str(emp_id),
            "name":             emp["name"],
            "cost_center_code": emp.get("cost_center_code", ""),
            "currency":         currency,
            "monthly":          monthly,
            "q1": q_totals[1], "q2": q_totals[2],
            "q3": q_totals[3], "q4": q_totals[4],
            "total":            total,
        }
        regions.setdefault(region, []).append({**base, "type": "CS Bonus Accrual (full potential)"})

        if region == "UK":
            ni_monthly = {k: round(v * 0.138, 2) for k, v in monthly.items()}
            ni_q       = {k: round(v * 0.138, 2) for k, v in q_totals.items()}
            regions[region].append({
                **base,
                "type":    "Employer NI (13.8%)",
                "monthly": ni_monthly,
                "q1": ni_q[1], "q2": ni_q[2],
                "q3": ni_q[3], "q4": ni_q[4],
                "total":   round(total * 0.138, 2),
            })
        if region == "Nordics":
            sc_monthly = {k: round(v * 0.31, 2) for k, v in monthly.items()}
            sc_q       = {k: round(v * 0.31, 2) for k, v in q_totals.items()}
            regions[region].append({
                **base,
                "type":    "Employer Social Contributions (31%)",
                "monthly": sc_monthly,
                "q1": sc_q[1], "q2": sc_q[2],
                "q3": sc_q[3], "q4": sc_q[4],
                "total":   round(total * 0.31, 2),
            })

    # ---- AE employees: accrual = annual_target_eur × 10% / 12 per month ----
    ae_employees = model.employees[model.employees["role"] == "ae"].copy()
    cs_perf      = getattr(model, "cs_performance", None)
    ae_targets   = cs_perf.get("ae_targets", pd.DataFrame()) if cs_perf else pd.DataFrame()

    for _, emp in ae_employees.iterrows():
        emp_id   = emp["employee_id"]
        region   = emp["region"]
        currency = emp["currency"]

        annual_target_eur = 0.0
        if not ae_targets.empty:
            mask = (
                (ae_targets["employee_id"].astype(str) == str(emp_id)) &
                (ae_targets["year"].astype(int) == int(year))
            )
            t = ae_targets[mask]
            if not t.empty:
                annual_target_eur = float(t["annual_target_eur"].iloc[0])

        # Monthly accrual in EUR, then convert to local currency using FX rate for that month
        monthly_accrual_eur = annual_target_eur * 0.10 / 12
        fx_rates_df = cs_perf.get("fx_rates", pd.DataFrame()) if cs_perf else pd.DataFrame()
        monthly = {}
        for m in year_months:
            if currency == "EUR":
                fx = 1.0
            elif not fx_rates_df.empty:
                fx = get_fx_rate(fx_rates_df, m, currency)
            else:
                fx = 1.0
            monthly[m.strftime("%Y-%m")] = round(monthly_accrual_eur * fx, 2)

        q_totals = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        for m in year_months:
            q_totals[_q(m)] += monthly[m.strftime("%Y-%m")]
        q_totals = {k: round(v, 2) for k, v in q_totals.items()}
        total = round(sum(monthly.values()), 2)

        base = {
            "employee_id":      str(emp_id),
            "name":             emp["name"],
            "cost_center_code": emp.get("cost_center_code", ""),
            "currency":         currency,
            "monthly":          monthly,
            "q1": q_totals[1], "q2": q_totals[2],
            "q3": q_totals[3], "q4": q_totals[4],
            "total":            total,
        }
        regions.setdefault(region, []).append({**base, "type": "AE Commission Accrual (10% of target)"})

        if region == "UK":
            ni_monthly = {k: round(v * 0.138, 2) for k, v in monthly.items()}
            ni_q       = {k: round(v * 0.138, 2) for k, v in q_totals.items()}
            regions[region].append({
                **base,
                "type":    "Employer NI (13.8%)",
                "monthly": ni_monthly,
                "q1": ni_q[1], "q2": ni_q[2],
                "q3": ni_q[3], "q4": ni_q[4],
                "total":   round(total * 0.138, 2),
            })
        if region == "Nordics":
            sc_monthly = {k: round(v * 0.31, 2) for k, v in monthly.items()}
            sc_q       = {k: round(v * 0.31, 2) for k, v in q_totals.items()}
            regions[region].append({
                **base,
                "type":    "Employer Social Contributions (31%)",
                "monthly": sc_monthly,
                "q1": sc_q[1], "q2": sc_q[2],
                "q3": sc_q[3], "q4": sc_q[4],
                "total":   round(total * 0.31, 2),
            })

    return {
        "months":       month_keys,
        "month_labels": month_labels,
        "regions":      [{"region": r, "rows": rows} for r, rows in regions.items()],
    }


# ---------------------------------------------------------------------------
# Employees list
# ---------------------------------------------------------------------------

def employee_list(model) -> list[dict]:
    commissioned = model.employees[
        model.employees["role"].isin(["sdr", "cs", "cs_lead", "ae"])
    ].copy()
    cols = ["employee_id", "name", "title", "role", "region", "currency"]
    if "manager_id" in commissioned.columns:
        cols.append("manager_id")
    return df_to_records(commissioned[cols])


# ---------------------------------------------------------------------------
# CS Team Overview — bonus + referral data for a given month
# ---------------------------------------------------------------------------

def cs_overview(model, month: pd.Timestamp) -> dict:
    if model.commission_detail.empty:
        return {"employees": [], "kpis": {"total_bonus_eur": 0, "avg_nrr_pct": 0, "avg_csat_pct": 0, "num_active": 0}}

    df = model.commission_detail[
        (model.commission_detail["month"] == month) &
        (model.commission_detail.get("role", pd.Series(dtype=str)) == "cs"
         if "role" in model.commission_detail.columns
         else model.commission_detail["employee_id"].isin(
             model.employees[model.employees["role"] == "cs"]["employee_id"]
         ))
    ].copy()

    if not df.empty:
        df["total_commission_eur"] = df["total_commission"] / df["fx_rate"].clip(lower=1e-6)
    else:
        df["total_commission_eur"] = 0.0

    _cs_cols = ["nrr_pct", "nrr_bonus", "csat_score_pct", "csat_bonus",
                "credits_used_pct", "credits_bonus", "quarterly_bonus_target",
                "referral_sao_count", "referral_sao_comm", "referral_cw_comm"]

    employees = []
    for _, row in df.iterrows():
        emp = {
            "employee_id":           row["employee_id"],
            "name":                  row["name"],
            "title":                 row["title"],
            "role":                  row.get("role", "cs"),
            "region":                row["region"],
            "currency":              row["currency"],
            "total_commission":      round(float(row.get("total_commission", 0)), 2),
            "total_commission_eur":  round(float(row["total_commission_eur"]), 2),
            "accelerator_topup":     round(float(row.get("accelerator_topup", 0)), 2),
        }
        for col in _cs_cols:
            emp[col] = round(float(row.get(col, 0) or 0), 2)
        employees.append(emp)

    total_eur = float(df["total_commission_eur"].sum()) if not df.empty else 0
    nrr_vals  = [e["nrr_pct"] for e in employees if e["nrr_pct"] > 0]
    csat_vals = [e["csat_score_pct"] for e in employees if e["csat_score_pct"] > 0]

    return {
        "employees": employees,
        "kpis": {
            "total_bonus_eur": round(total_eur, 2),
            "avg_nrr_pct":     round(sum(nrr_vals)  / len(nrr_vals)  if nrr_vals  else 0, 1),
            "avg_csat_pct":    round(sum(csat_vals) / len(csat_vals) if csat_vals else 0, 1),
            "num_active":      int(df["employee_id"].nunique()) if not df.empty else 0,
        },
    }


# ---------------------------------------------------------------------------
# CS Quarterly scorecard
# ---------------------------------------------------------------------------

def cs_quarterly(model, year: int, quarter: int) -> dict:
    months = quarter_months(year, quarter)

    if model.commission_detail.empty:
        return {"employees": [], "year": year, "quarter": quarter}

    cs_ids = set(model.employees[model.employees["role"] == "cs"]["employee_id"])
    df = model.commission_detail[
        model.commission_detail["month"].isin(months) &
        model.commission_detail["employee_id"].isin(cs_ids)
    ].copy()

    if df.empty:
        return {"employees": [], "year": year, "quarter": quarter}

    _sum_cols = ["referral_sao_count", "referral_sao_comm", "referral_cw_comm",
                 "accelerator_topup", "total_commission"]
    _qend_cols = ["nrr_pct", "nrr_bonus", "csat_score_pct", "csat_bonus",
                  "credits_used_pct", "credits_bonus", "quarterly_bonus_target"]
    _qend_months = {3, 6, 9, 12}

    emp_rows = []
    for emp_id, grp in df.groupby("employee_id"):
        qe = grp[grp["month"].apply(lambda m: m.month in _qend_months)]
        row = {
            "employee_id": emp_id,
            "name":        grp["name"].iloc[0],
            "role":        grp["role"].iloc[0] if "role" in grp.columns else "cs",
            "region":      grp["region"].iloc[0],
            "currency":    grp["currency"].iloc[0],
        }
        for col in _sum_cols:
            row[col] = round(float(grp[col].sum()) if col in grp.columns else 0, 2)
        for col in _qend_cols:
            row[col] = round(float(qe[col].iloc[0]) if not qe.empty and col in qe.columns else 0, 2)
        emp_rows.append(row)

    return {"employees": emp_rows, "year": year, "quarter": quarter}


# ---------------------------------------------------------------------------
# AE Team Overview — annual view per AE with per-quarter gate status
# ---------------------------------------------------------------------------

def ae_overview(model, year: int) -> dict:
    """Annual AE overview: per-AE YTD ACV and year-end commission."""
    all_months  = sorted(model.active_months)
    year_months = [m for m in all_months if m.year == year]

    ae_ids = set(model.employees[model.employees["role"] == "ae"]["employee_id"])
    if not ae_ids:
        return {"employees": [], "kpis": {}, "year": year}

    cs_perf = getattr(model, "cs_performance", None)
    ae_cw   = cs_perf.get("ae_closed_won", pd.DataFrame()) if cs_perf else pd.DataFrame()
    targets_df = cs_perf.get("ae_targets", pd.DataFrame()) if cs_perf else pd.DataFrame()

    def _q_months(q):
        return [m for m in year_months if (m.month - 1) // 3 + 1 == q]

    employees_out = []
    for _, emp in model.employees[model.employees["role"] == "ae"].iterrows():
        emp_id   = emp["employee_id"]
        currency = emp["currency"]

        # Targets
        annual_target_eur = 0.0
        q_target_eur      = 0.0
        if not targets_df.empty:
            mask = (
                (targets_df["employee_id"].astype(str) == str(emp_id)) &
                (targets_df["year"].astype(int) == int(year))
            )
            t = targets_df[mask]
            if not t.empty:
                annual_target_eur = float(t["annual_target_eur"].iloc[0])
                q_target_eur      = float(t["quarterly_target_eur"].iloc[0])

        # Per-quarter ACV and gate
        q_acv   = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        q_gate  = {1: False, 2: False, 3: False, 4: False}
        if not ae_cw.empty:
            emp_yr = ae_cw[ae_cw["employee_id"] == emp_id]
            for q in range(1, 5):
                qm = _q_months(q)
                qd = emp_yr[emp_yr["month"].isin(qm)]
                acv = float(qd["acv_eur"].sum())
                q_acv[q] = round(acv, 2)
                q_gate[q] = acv >= q_target_eur * 0.5 if q_target_eur > 0 else False

        ytd_acv_eur = round(sum(q_acv.values()), 2)
        ytd_acv_my  = 0.0
        if not ae_cw.empty:
            emp_yr = ae_cw[
                (ae_cw["employee_id"] == emp_id) &
                (ae_cw["month"].isin(year_months))
            ]
            if "multi_year_acv_eur" in emp_yr.columns:
                ytd_acv_my = round(float(emp_yr["multi_year_acv_eur"].sum()), 2)

        attainment_pct = round((ytd_acv_eur / annual_target_eur) * 100, 1) if annual_target_eur > 0 else 0.0

        qualifying_acv_eur = round(sum(q_acv[q] for q in range(1, 5) if q_gate[q]), 2)

        # Year-end commission: pull from commission_detail for December of year
        year_end_commission     = 0.0
        year_end_commission_eur = 0.0
        if not model.commission_detail.empty:
            dec_month = pd.Timestamp(year=year, month=12, day=1)
            det = model.commission_detail[
                (model.commission_detail["employee_id"] == emp_id) &
                (model.commission_detail["month"] == dec_month)
            ]
            if not det.empty:
                year_end_commission = round(float(det["accelerator_topup"].iloc[0]), 2)
                fx = float(det["fx_rate"].iloc[0]) or 1.0
                year_end_commission_eur = round(year_end_commission / fx, 2)

        employees_out.append({
            "employee_id":           str(emp_id),
            "name":                  emp["name"],
            "role":                  emp["role"],
            "region":                emp["region"],
            "currency":              currency,
            "annual_target_eur":     annual_target_eur,
            "ytd_acv_eur":           ytd_acv_eur,
            "ytd_acv_my_eur":        ytd_acv_my,
            "annual_attainment_pct": attainment_pct,
            "qualifying_acv_eur":    qualifying_acv_eur,
            "year_end_commission":     year_end_commission,
            "year_end_commission_eur": year_end_commission_eur,
            "q1_gate": q_gate[1], "q2_gate": q_gate[2],
            "q3_gate": q_gate[3], "q4_gate": q_gate[4],
            "q1_acv":  q_acv[1],  "q2_acv":  q_acv[2],
            "q3_acv":  q_acv[3],  "q4_acv":  q_acv[4],
        })

    total_acv_eur        = round(sum(e["ytd_acv_eur"] for e in employees_out), 2)
    attainments          = [e["annual_attainment_pct"] for e in employees_out if e["annual_target_eur"] > 0]
    avg_attainment_pct   = round(sum(attainments) / len(attainments), 1) if attainments else 0.0
    total_year_end_comm  = round(sum(e["year_end_commission_eur"] for e in employees_out), 2)

    return {
        "employees": employees_out,
        "kpis": {
            "total_acv_eur":          total_acv_eur,
            "avg_attainment_pct":     avg_attainment_pct,
            "num_aes":                len(employees_out),
            "total_year_end_comm_eur": total_year_end_comm,
        },
        "year": year,
    }


# ---------------------------------------------------------------------------
# AE Detail — per-quarter breakdown for one AE
# ---------------------------------------------------------------------------

def ae_detail(model, employee_id: str, year: int) -> dict:
    """Per-quarter breakdown for one AE."""
    emp_row = model.employees[model.employees["employee_id"] == employee_id]
    if emp_row.empty:
        return {"employee": {}, "quarters": [], "year_end": {}}

    emp      = emp_row.iloc[0].to_dict()
    emp      = {k: (str(v) if isinstance(v, pd.Timestamp) else v) for k, v in emp.items()}
    currency = emp.get("currency", "EUR")

    all_months  = sorted(model.active_months)
    year_months = [m for m in all_months if m.year == year]

    cs_perf    = getattr(model, "cs_performance", None)
    ae_cw      = cs_perf.get("ae_closed_won", pd.DataFrame()) if cs_perf else pd.DataFrame()
    targets_df = cs_perf.get("ae_targets", pd.DataFrame()) if cs_perf else pd.DataFrame()

    q_target_eur      = 0.0
    annual_target_eur = 0.0
    if not targets_df.empty:
        mask = (
            (targets_df["employee_id"].astype(str) == str(employee_id)) &
            (targets_df["year"].astype(int) == int(year))
        )
        t = targets_df[mask]
        if not t.empty:
            q_target_eur      = float(t["quarterly_target_eur"].iloc[0])
            annual_target_eur = float(t["annual_target_eur"].iloc[0])

    _q_labels = {1: f"Q1 FY{str(year)[2:]}", 2: f"Q2 FY{str(year)[2:]}",
                 3: f"Q3 FY{str(year)[2:]}", 4: f"Q4 FY{str(year)[2:]}"}

    quarters_out = []
    for q in range(1, 5):
        qm = [m for m in year_months if (m.month - 1) // 3 + 1 == q]
        q_acv = 0.0
        deals_count    = 0
        invoiced_count = 0
        forecast_count = 0
        if not ae_cw.empty:
            emp_q = ae_cw[
                (ae_cw["employee_id"] == employee_id) &
                (ae_cw["month"].isin(qm))
            ]
            q_acv          = float(emp_q["acv_eur"].sum())
            deals_count    = len(emp_q)
            if "is_forecast" in emp_q.columns:
                forecast_count = int(emp_q["is_forecast"].sum())
                invoiced_count = deals_count - forecast_count
            else:
                invoiced_count = deals_count

        gate_met = q_acv >= q_target_eur * 0.5 if q_target_eur > 0 else False
        att_pct  = round((q_acv / q_target_eur) * 100, 1) if q_target_eur > 0 else 0.0

        months_labels = [m.strftime("%b") for m in qm] if qm else []

        quarters_out.append({
            "quarter":         q,
            "q_label":         _q_labels[q],
            "months":          months_labels,
            "q_acv_eur":       round(q_acv, 2),
            "q_target_eur":    q_target_eur,
            "q_attainment_pct": att_pct,
            "gate_met":        gate_met,
            "deals_count":     deals_count,
            "invoiced_count":  invoiced_count,
            "forecast_count":  forecast_count,
        })

    # Year-end commission row from December commission_detail
    year_end: dict = {}
    if not model.commission_detail.empty:
        dec_month = pd.Timestamp(year=year, month=12, day=1)
        det = model.commission_detail[
            (model.commission_detail["employee_id"] == employee_id) &
            (model.commission_detail["month"] == dec_month)
        ]
        if not det.empty:
            row = det.iloc[0].to_dict()
            year_end = {k: (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v)
                        for k, v in row.items()}

    # Also pull Q4 accelerator row if available
    if not model.accelerators.empty:
        acc_q4 = model.accelerators[
            (model.accelerators["employee_id"] == employee_id) &
            (model.accelerators["year"] == year) &
            (model.accelerators["quarter"] == 4)
        ]
        if not acc_q4.empty:
            acc_row = acc_q4.iloc[0].to_dict()
            acc_row = {k: (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v)
                       for k, v in acc_row.items()}
            year_end["accelerator"] = acc_row

    ytd_acv = sum(q["q_acv_eur"] for q in quarters_out)
    att_pct = round((ytd_acv / annual_target_eur) * 100, 1) if annual_target_eur > 0 else 0.0

    emp["annual_target_eur"]     = annual_target_eur
    emp["annual_attainment_pct"] = att_pct
    emp["ytd_acv_eur"]           = round(ytd_acv, 2)
    emp["year_end_commission"]   = float(year_end.get("accelerator_topup", 0) or 0)

    return {
        "employee": emp,
        "quarters": quarters_out,
        "year_end": year_end,
        "year":     year,
    }


# ---------------------------------------------------------------------------
# AE Monthly breakdown — per-AE monthly ACV for the full year
# ---------------------------------------------------------------------------

def ae_monthly(model, year: int) -> dict:
    """Per-AE monthly ACV breakdown for the full year."""
    all_months  = sorted(model.active_months)
    year_months = [m for m in all_months if m.year == year]

    cs_perf    = getattr(model, "cs_performance", None)
    ae_cw      = cs_perf.get("ae_closed_won", pd.DataFrame()) if cs_perf else pd.DataFrame()
    targets_df = cs_perf.get("ae_targets", pd.DataFrame()) if cs_perf else pd.DataFrame()

    month_keys   = [m.strftime("%Y-%m") for m in year_months]
    month_labels = [m.strftime("%b-%y") for m in year_months]

    employees_out = []
    for _, emp in model.employees[model.employees["role"] == "ae"].iterrows():
        emp_id   = emp["employee_id"]
        currency = emp["currency"]

        q_target_eur = 0.0
        if not targets_df.empty:
            mask = (
                (targets_df["employee_id"].astype(str) == str(emp_id)) &
                (targets_df["year"].astype(int) == int(year))
            )
            t = targets_df[mask]
            if not t.empty:
                q_target_eur = float(t["quarterly_target_eur"].iloc[0])

        monthly_acv_eur    = {}
        monthly_acv_my_eur = {}
        for m in year_months:
            mk = m.strftime("%Y-%m")
            if not ae_cw.empty:
                m_data = ae_cw[(ae_cw["employee_id"] == emp_id) & (ae_cw["month"] == m)]
                monthly_acv_eur[mk]    = round(float(m_data["acv_eur"].sum()), 2)
                monthly_acv_my_eur[mk] = round(
                    float(m_data["multi_year_acv_eur"].sum()) if "multi_year_acv_eur" in m_data.columns else 0.0, 2
                )
            else:
                monthly_acv_eur[mk]    = 0.0
                monthly_acv_my_eur[mk] = 0.0

        employees_out.append({
            "employee_id":       str(emp_id),
            "name":              emp["name"],
            "currency":          currency,
            "region":            emp["region"],
            "q_target_eur":      q_target_eur,
            "monthly_acv_eur":   monthly_acv_eur,
            "monthly_acv_my_eur": monthly_acv_my_eur,
        })

    return {
        "months":       month_keys,
        "month_labels": month_labels,
        "employees":    employees_out,
        "year":         year,
    }


# ---------------------------------------------------------------------------
# Available months
# ---------------------------------------------------------------------------

def available_months(model) -> list[str]:
    return [m.strftime("%Y-%m-%d") for m in model.active_months]
