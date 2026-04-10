"""Shared report builders used across all roles."""
import pandas as pd
from src.helpers import df_to_records, get_fx_rate
from src.commission_plans import get_plan


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
    if emp["role"] in ("cs", "cs_lead") and cs_perf:
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
            "role":             emp["role"],
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
            "role":             emp["role"],
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

    # ---- CS / CS Lead employees: accrual = full potential (salary x 15% or 20%) ----
    cs_employees = model.employees[model.employees["role"].isin(["cs", "cs_lead"])].copy()
    for _, emp in cs_employees.iterrows():
        emp_id    = emp["employee_id"]
        region    = emp["region"]
        currency  = emp["currency"]
        bonus_pct = 0.20 if emp["role"] == "cs_lead" else 0.15
        sal_hist  = model.salary_history[model.salary_history["employee_id"] == emp_id]

        monthly = {}
        for m in year_months:
            eligible = (
                sal_hist[sal_hist["effective_date"] <= m]
                .sort_values("effective_date", ascending=False)
            )
            sal_monthly = float(eligible["salary_monthly"].iloc[0]) if not eligible.empty else 0.0
            monthly[m.strftime("%Y-%m")] = round(sal_monthly * bonus_pct, 2)

        q_totals = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        for m in year_months:
            q_totals[_q(m)] += monthly[m.strftime("%Y-%m")]
        q_totals = {k: round(v, 2) for k, v in q_totals.items()}
        total = round(sum(monthly.values()), 2)

        base = {
            "employee_id":      str(emp_id),
            "name":             emp["name"],
            "role":             emp["role"],
            "cost_center_code": emp.get("cost_center_code", ""),
            "currency":         currency,
            "monthly":          monthly,
            "q1": q_totals[1], "q2": q_totals[2],
            "q3": q_totals[3], "q4": q_totals[4],
            "total":            total,
        }
        accrual_label = (
            f"CS Lead Bonus Accrual (full potential, 20%)"
            if emp["role"] == "cs_lead"
            else "CS Bonus Accrual (full potential)"
        )
        regions.setdefault(region, []).append({**base, "type": accrual_label})

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

    # ---- AE employees: accrual = annual_target_eur x 10% / 12 per month ----
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
            "role":             emp["role"],
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
# Available months
# ---------------------------------------------------------------------------

def available_months(model) -> list[str]:
    return [m.strftime("%Y-%m-%d") for m in model.active_months]
