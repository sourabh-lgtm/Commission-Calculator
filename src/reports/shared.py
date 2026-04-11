"""Shared report builders used across all roles."""
import pandas as pd
from src.helpers import df_to_records, get_fx_rate
from src.commission_plans import get_plan


def _prorated_salary(sal_hist: pd.DataFrame, m: pd.Timestamp) -> float:
    """Return the monthly salary for month m, prorated for mid-month starts.

    sal_hist must already be filtered to a single employee.
    Uses the most-recent salary effective on or before the last day of m.
    If the effective_date falls inside the month (e.g. joined on the 2nd),
    the amount is scaled by (days active / total days in month).
    """
    month_end = (m + pd.offsets.MonthEnd(0)).normalize()
    eligible  = sal_hist[sal_hist["effective_date"] <= month_end].sort_values(
        "effective_date", ascending=False
    )
    if eligible.empty:
        return 0.0
    eff = pd.Timestamp(eligible.iloc[0]["effective_date"]).normalize()
    sal = float(eligible.iloc[0]["salary_monthly"])
    if eff > m.normalize():                          # mid-month start
        days_in_month = month_end.day               # 28/29/30/31
        days_active   = (month_end - eff).days + 1
        return round(sal * days_active / days_in_month, 4)
    return sal


# ---------------------------------------------------------------------------
# Commission workings: row-level audit trail
# ---------------------------------------------------------------------------

def commission_workings(
    model,
    employee_id: str,
    month: pd.Timestamp,
    quarter: int = None,
    year: int = None,
) -> dict:
    emp_row = model.employees[model.employees["employee_id"] == employee_id]
    if emp_row.empty:
        return {"rows": [], "summary": {}}

    # For role-split employees (e.g. sdr_lead Q1 → ae Q2+), pick the entry
    # whose plan window covers the requested month.
    if len(emp_row) > 1 and month is not None:
        covering = emp_row[
            (emp_row["plan_start_date"].isna() | (emp_row["plan_start_date"] <= month)) &
            (emp_row["plan_end_date"].isna()   | (emp_row["plan_end_date"]   >= month))
        ]
        if not covering.empty:
            emp_row = covering

    emp = emp_row.iloc[0]
    plan_cls = get_plan(emp["role"])
    if plan_cls is None:
        return {"rows": [], "summary": {}}

    plan = plan_cls()
    cs_perf = getattr(model, "cs_performance", None)
    if emp["role"] in ("cs", "cs_lead", "cs_director") and cs_perf:
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
            quarter=quarter,
            year=year,
        )
    elif emp["role"] == "sdr_lead" and cs_perf:
        rows = plan.get_workings_rows(
            emp, month,
            model.sdr_activities,
            model.closed_won,
            model.fx_rates,
            cs_performance=cs_perf,
        )
    elif emp["role"] in ("am", "am_lead") and cs_perf:
        rows = plan.get_workings_rows(
            emp, month,
            model.sdr_activities,
            model.closed_won,
            model.fx_rates,
            cs_performance=cs_perf,
        )
    elif emp["role"] == "se" and cs_perf:
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
    # For AE quarterly view: look up by quarter-end month
    if emp["role"] == "ae" and quarter is not None and year is not None:
        q_end_month = pd.Timestamp(year=year, month=quarter * 3, day=1)
        det = model.commission_detail[
            (model.commission_detail["employee_id"] == employee_id) &
            (model.commission_detail["month"] == q_end_month)
        ]
    else:
        det = model.commission_detail[
            (model.commission_detail["employee_id"] == employee_id) &
            (model.commission_detail["month"] == month)
        ]
    summary = det.iloc[0].to_dict() if not det.empty else {}
    summary = {k: (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v)
               for k, v in summary.items()}

    # Also include the accelerator row for AE quarterly view
    if emp["role"] == "ae" and quarter is not None and year is not None:
        if not model.accelerators.empty:
            acc_row = model.accelerators[
                (model.accelerators["employee_id"] == employee_id) &
                (model.accelerators["year"] == year) &
                (model.accelerators["quarter"] == quarter)
            ]
            if not acc_row.empty:
                acc = acc_row.iloc[0].to_dict()
                summary["accelerator"] = {
                    k: (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v)
                    for k, v in acc.items()
                }

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

    commissioned = (
        model.employees[
            model.employees["role"].isin(
                ["sdr", "sdr_lead", "cs", "cs_lead", "cs_director", "ae", "am", "am_lead", "se"]
            )
        ]
        .sort_values("plan_end_date", ascending=True, na_position="last")
        .drop_duplicates(subset=["employee_id"], keep="last")
        .copy()
    )
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

    # ---- SDR / SDR Lead employees: accrual = actual commission ----
    sdrs = model.employees[model.employees["role"].isin(["sdr", "sdr_lead"])].copy()
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

    # ---- CS / CS Lead / CS Director employees: accrual = full potential (salary x 15% or 20%) ----
    cs_employees = model.employees[model.employees["role"].isin(["cs", "cs_lead", "cs_director"])].copy()
    for _, emp in cs_employees.iterrows():
        emp_id    = emp["employee_id"]
        region    = emp["region"]
        currency  = emp["currency"]
        bonus_pct = 0.20 if emp["role"] in ("cs_lead", "cs_director") else 0.15
        sal_hist  = model.salary_history[model.salary_history["employee_id"] == emp_id]

        monthly = {}
        for m in year_months:
            sal_monthly = _prorated_salary(sal_hist, m)
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
            "CS Director Bonus Accrual (full potential, 20%)" if emp["role"] == "cs_director"
            else "CS Lead Bonus Accrual (full potential, 20%)" if emp["role"] == "cs_lead"
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

    # ---- AM / AM Lead employees: accrual = salary x 20% per month ----
    am_employees = model.employees[model.employees["role"].isin(["am", "am_lead"])].copy()
    for _, emp in am_employees.iterrows():
        emp_id    = emp["employee_id"]
        region    = emp["region"]
        currency  = emp["currency"]
        sal_hist  = model.salary_history[model.salary_history["employee_id"] == emp_id]

        monthly = {}
        for m in year_months:
            sal_monthly = _prorated_salary(sal_hist, m)
            monthly[m.strftime("%Y-%m")] = round(sal_monthly * 0.20, 2)

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
            "AM Lead Bonus Accrual (full potential, 20%)" if emp["role"] == "am_lead"
            else "AM Bonus Accrual (full potential, 20%)"
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

    # ---- SE employees: accrual = salary x 20% per month ----
    se_employees = model.employees[model.employees["role"] == "se"].copy()
    for _, emp in se_employees.iterrows():
        emp_id    = emp["employee_id"]
        region    = emp["region"]
        currency  = emp["currency"]
        sal_hist  = model.salary_history[model.salary_history["employee_id"] == emp_id]

        monthly = {}
        for m in year_months:
            sal_monthly = _prorated_salary(sal_hist, m)
            monthly[m.strftime("%Y-%m")] = round(sal_monthly * 0.20, 2)

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
        regions.setdefault(region, []).append({**base, "type": "SE Bonus Accrual (full potential, 20%)"})

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
# Accrual vs Payroll: per-employee quarterly comparison, grouped by department
# ---------------------------------------------------------------------------

def accrual_vs_payroll(model, year: int) -> dict:
    """Compare quarterly accruals vs actual/forecast payroll per employee.

    Accrual amounts follow the same logic as accrual_summary (primary rows only,
    no employer contributions).  Payroll amounts are the actual commissions from
    commission_detail.  Department and grand totals are converted to EUR.
    """
    all_months  = sorted(model.active_months)
    year_months = [m for m in all_months if m.year == year]
    if not year_months:
        return {"year": year, "departments": [], "grand_total": {}}

    df      = model.commission_detail[model.commission_detail["month"].isin(year_months)].copy()
    cs_perf = getattr(model, "cs_performance", None)
    fx_df   = cs_perf.get("fx_rates", pd.DataFrame()) if cs_perf else pd.DataFrame()
    ae_tgts = cs_perf.get("ae_targets", pd.DataFrame()) if cs_perf else pd.DataFrame()

    def _q(m):
        return (m.month - 1) // 3 + 1

    def _to_eur(amount, currency, month):
        if currency == "EUR" or amount == 0:
            return amount
        if not fx_df.empty:
            fx = get_fx_rate(fx_df, month, currency)
            return round(amount / fx, 2) if fx else amount
        return amount

    def _accrual_monthly(emp_id, currency, role):
        monthly = {}
        if role in ("sdr", "sdr_lead"):
            edf = df[df["employee_id"] == emp_id]
            for m in year_months:
                monthly[m] = round(float(edf[edf["month"] == m]["total_commission"].sum()), 2)
        elif role in ("cs", "cs_lead", "cs_director"):
            pct = 0.20 if role in ("cs_lead", "cs_director") else 0.15
            sh  = model.salary_history[model.salary_history["employee_id"] == emp_id]
            for m in year_months:
                monthly[m] = round(_prorated_salary(sh, m) * pct, 2)
        elif role == "ae":
            target_eur = 0.0
            if not ae_tgts.empty:
                mask = (
                    (ae_tgts["employee_id"].astype(str) == str(emp_id)) &
                    (ae_tgts["year"].astype(int) == int(year))
                )
                t = ae_tgts[mask]
                if not t.empty:
                    target_eur = float(t["annual_target_eur"].iloc[0])
            m_eur = target_eur * 0.10 / 12
            for m in year_months:
                fx = 1.0 if currency == "EUR" else (get_fx_rate(fx_df, m, currency) if not fx_df.empty else 1.0)
                monthly[m] = round(m_eur * fx, 2)
        elif role in ("am", "am_lead", "se"):
            sh = model.salary_history[model.salary_history["employee_id"] == emp_id]
            for m in year_months:
                monthly[m] = round(_prorated_salary(sh, m) * 0.20, 2)
        else:
            for m in year_months:
                monthly[m] = 0.0
        return monthly

    def _payroll_monthly(emp_id):
        edf = df[df["employee_id"] == emp_id]
        result = {}
        for m in year_months:
            row = edf[edf["month"] == m]
            result[m] = round(float(row["total_commission"].iloc[0]), 2) if not row.empty else 0.0
        return result

    def _quarterly_local(monthly):
        q = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        for m, v in monthly.items():
            q[_q(m)] += v
        return {k: round(v, 2) for k, v in q.items()}

    def _quarterly_eur(monthly, currency):
        q = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        for m, v in monthly.items():
            q[_q(m)] += _to_eur(v, currency, m)
        return {k: round(v, 2) for k, v in q.items()}

    def _totals(q):
        return {**{f"q{k}": q[k] for k in [1, 2, 3, 4]}, "total": round(sum(q.values()), 2)}

    DEPARTMENTS = [
        ("SDR \u2014 Sales Development",        ["sdr", "sdr_lead"]),
        ("CS \u2014 Climate Strategy Advisors", ["cs", "cs_lead", "cs_director"]),
        ("AE \u2014 Account Executives",        ["ae"]),
        ("AM \u2014 Account Managers",          ["am", "am_lead"]),
        ("SE \u2014 Solutions Engineers",       ["se"]),
    ]

    departments = []
    grand_acc = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    grand_pay = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}

    for dept_name, roles in DEPARTMENTS:
        emps = (
            model.employees[model.employees["role"].isin(roles)]
            .sort_values("plan_end_date", ascending=True, na_position="last")
            .drop_duplicates(subset=["employee_id"], keep="last")
            .copy()
        )
        if emps.empty:
            continue

        dept_acc = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        dept_pay = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        emp_rows = []

        for _, emp in emps.iterrows():
            emp_id   = emp["employee_id"]
            currency = emp["currency"]
            role     = emp["role"]

            acc_m = _accrual_monthly(emp_id, currency, role)
            pay_m = _payroll_monthly(emp_id)

            acc_q_eur = _quarterly_eur(acc_m, currency)
            pay_q_eur = _quarterly_eur(pay_m, currency)
            del_q_eur = {k: round(acc_q_eur[k] - pay_q_eur[k], 2) for k in [1, 2, 3, 4]}

            for k in [1, 2, 3, 4]:
                dept_acc[k] = round(dept_acc[k] + acc_q_eur[k], 2)
                dept_pay[k] = round(dept_pay[k] + pay_q_eur[k], 2)

            emp_rows.append({
                "employee_id":      str(emp_id),
                "name":             emp["name"],
                "role":             role,
                "cost_center_code": emp.get("cost_center_code", ""),
                "currency":         "EUR",
                "accrual": _totals(acc_q_eur),
                "payroll": _totals(pay_q_eur),
                "delta":   _totals(del_q_eur),
            })

        dept_del = {k: round(dept_acc[k] - dept_pay[k], 2) for k in [1, 2, 3, 4]}
        for k in [1, 2, 3, 4]:
            grand_acc[k] = round(grand_acc[k] + dept_acc[k], 2)
            grand_pay[k] = round(grand_pay[k] + dept_pay[k], 2)

        departments.append({
            "name":      dept_name,
            "employees": emp_rows,
            "dept_total": {
                "accrual": _totals(dept_acc),
                "payroll": _totals(dept_pay),
                "delta":   _totals(dept_del),
            },
        })

    grand_del = {k: round(grand_acc[k] - grand_pay[k], 2) for k in [1, 2, 3, 4]}
    return {
        "year": year,
        "departments": departments,
        "grand_total": {
            "accrual": _totals(grand_acc),
            "payroll": _totals(grand_pay),
            "delta":   _totals(grand_del),
        },
    }


# ---------------------------------------------------------------------------
# Employees list
# ---------------------------------------------------------------------------

def employee_list(model) -> list[dict]:
    commissioned = model.employees[
        model.employees["role"].isin(
            ["sdr", "sdr_lead", "cs", "cs_lead", "cs_director", "ae", "am", "am_lead", "se"]
        )
    ].copy()
    # AEs and SDRs: only show those active on or after 2026-01-01 (exclude pre-FY26 leavers)
    if "plan_end_date" in commissioned.columns:
        fy26_start = pd.Timestamp("2026-01-01")
        role_mask = commissioned["role"].isin(["ae", "sdr"])
        fy26_active = commissioned["plan_end_date"].isna() | (commissioned["plan_end_date"] >= fy26_start)
        commissioned = commissioned[~role_mask | fy26_active]
    cols = ["employee_id", "name", "title", "role", "region", "currency"]
    if "manager_id" in commissioned.columns:
        cols.append("manager_id")
    return df_to_records(commissioned[cols])


# ---------------------------------------------------------------------------
# Org chart — all employees for hierarchy building in the frontend
# ---------------------------------------------------------------------------

def org_chart(model) -> list[dict]:
    """Return all employees (commissioned + non-commissioned) for org-tree building.

    Includes managers, directors, VPs etc. so the frontend can traverse the
    full hierarchy using manager_id links.
    """
    emp = model.employees.copy()
    cols = [c for c in ["employee_id", "name", "role", "manager_id"] if c in emp.columns]
    return df_to_records(emp[cols])


# ---------------------------------------------------------------------------
# Available months
# ---------------------------------------------------------------------------

def available_months(model) -> list[str]:
    return [m.strftime("%Y-%m-%d") for m in model.active_months]
