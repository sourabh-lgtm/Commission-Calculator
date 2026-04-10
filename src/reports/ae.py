"""AE commission report builders."""
import pandas as pd


# ---------------------------------------------------------------------------
# AE Team Overview: annual view per AE with per-quarter gate status
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

        # Per-quarter ACV and gate (attributed by close_date, deduplicated by opportunity)
        def _in_qm(d, qm):
            if pd.isna(d):
                return False
            return pd.Timestamp(d).to_period("M").to_timestamp() in qm

        q_acv   = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        q_gate  = {1: False, 2: False, 3: False, 4: False}
        has_cw_data = (
            not ae_cw.empty and
            "close_date" in ae_cw.columns and
            ("opportunity_acv_eur" in ae_cw.columns or "acv_eur" in ae_cw.columns)
        )
        if has_cw_data:
            emp_yr = ae_cw[ae_cw["employee_id"] == emp_id]
            for q in range(1, 5):
                qm = _q_months(q)
                qd = emp_yr[emp_yr["close_date"].apply(lambda d: _in_qm(d, qm))]
                qd_dedup = qd.drop_duplicates("opportunity_id")
                if "opportunity_acv_eur" in qd_dedup.columns:
                    acv = float(qd_dedup["opportunity_acv_eur"].sum())
                else:
                    acv = float(qd_dedup["acv_eur"].sum()) if "acv_eur" in qd_dedup.columns else 0.0
                q_acv[q] = round(acv, 2)
                q_gate[q] = acv >= q_target_eur * 0.5 if q_target_eur > 0 else False

        ytd_acv_eur = round(sum(q_acv.values()), 2)
        ytd_acv_my  = 0.0
        if has_cw_data:
            # Multi-year ACV: unique deals whose close_date falls in the year
            all_year_qm = [m for q in range(1, 5) for m in _q_months(q)]
            emp_yr_all = ae_cw[
                (ae_cw["employee_id"] == emp_id) &
                ae_cw["close_date"].apply(lambda d: _in_qm(d, all_year_qm))
            ].drop_duplicates("opportunity_id")
            if "opportunity_multi_year_acv_eur" in emp_yr_all.columns:
                ytd_acv_my = round(float(emp_yr_all["opportunity_multi_year_acv_eur"].sum()), 2)
            elif "multi_year_acv_eur" in emp_yr_all.columns:
                ytd_acv_my = round(float(emp_yr_all["multi_year_acv_eur"].sum()), 2)

        attainment_pct = round((ytd_acv_eur / annual_target_eur) * 100, 1) if annual_target_eur > 0 else 0.0

        qualifying_acv_eur = round(sum(q_acv[q] for q in range(1, 5) if q_gate[q]), 2)

        # Total commission: sum all quarterly payouts across the year
        year_end_commission     = 0.0
        year_end_commission_eur = 0.0
        if not model.commission_detail.empty:
            emp_det = model.commission_detail[
                (model.commission_detail["employee_id"] == emp_id) &
                (model.commission_detail["month"].isin(year_months)) &
                (model.commission_detail["accelerator_topup"] > 0)
            ]
            if not emp_det.empty:
                year_end_commission = round(float(emp_det["accelerator_topup"].sum()), 2)
                # EUR: divide each row's commission by its fx_rate then sum
                year_end_commission_eur = round(
                    float((emp_det["accelerator_topup"] / emp_det["fx_rate"].clip(lower=1e-9)).sum()), 2
                )

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
# AE Detail: per-quarter breakdown for one AE
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

    def _in_qm_det(d, qm):
        if pd.isna(d):
            return False
        return pd.Timestamp(d).to_period("M").to_timestamp() in qm

    has_cw = (
        not ae_cw.empty and
        "close_date" in ae_cw.columns and
        ("opportunity_acv_eur" in ae_cw.columns or "acv_eur" in ae_cw.columns)
    )

    quarters_out = []
    for q in range(1, 5):
        qm = [m for m in year_months if (m.month - 1) // 3 + 1 == q]
        q_acv = 0.0
        deals_count    = 0
        invoiced_count = 0
        forecast_count = 0
        if has_cw:
            # Use close_date to attribute deals to quarters; deduplicate by opportunity
            emp_q_raw = ae_cw[
                (ae_cw["employee_id"] == employee_id) &
                ae_cw["close_date"].apply(lambda d: _in_qm_det(d, qm))
            ]
            emp_q = emp_q_raw.drop_duplicates("opportunity_id")
            if "opportunity_acv_eur" in emp_q.columns:
                q_acv = float(emp_q["opportunity_acv_eur"].sum())
            else:
                q_acv = float(emp_q["acv_eur"].sum()) if "acv_eur" in emp_q.columns else 0.0
            deals_count = len(emp_q)
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

    # Find all earning quarters for this employee in this year
    # (multiple rows when paid quarterly; final row has annual accelerators)
    year_end: dict = {}
    all_accelerators: list = []
    if not model.accelerators.empty:
        emp_acc = model.accelerators[
            (model.accelerators["employee_id"] == employee_id) &
            (model.accelerators["year"] == year)
        ].sort_values("quarter")
        if not emp_acc.empty:
            # Collect all quarterly accelerator rows for the UI
            for _, acc_row_s in emp_acc.iterrows():
                acc_row = acc_row_s.to_dict()
                acc_row = {k: (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v)
                           for k, v in acc_row.items()}
                all_accelerators.append(acc_row)

            # year_end points to the final quarter's commission detail row
            final_q    = int(emp_acc.iloc[-1]["quarter"])
            comm_month = pd.Timestamp(year=year, month=final_q * 3, day=1)
            if not model.commission_detail.empty:
                det = model.commission_detail[
                    (model.commission_detail["employee_id"] == employee_id) &
                    (model.commission_detail["month"] == comm_month)
                ]
                if not det.empty:
                    row = det.iloc[0].to_dict()
                    year_end = {k: (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v)
                                for k, v in row.items()}
            year_end["accelerator"]      = all_accelerators[-1] if all_accelerators else {}
            year_end["all_accelerators"] = all_accelerators

    ytd_acv = sum(q["q_acv_eur"] for q in quarters_out)
    att_pct = round((ytd_acv / annual_target_eur) * 100, 1) if annual_target_eur > 0 else 0.0

    # Total commission = sum of all quarterly payouts
    total_commission = 0.0
    if not model.commission_detail.empty:
        all_months_for_year = [pd.Timestamp(year=year, month=q * 3, day=1) for q in range(1, 5)]
        det_all = model.commission_detail[
            (model.commission_detail["employee_id"] == employee_id) &
            (model.commission_detail["month"].isin(all_months_for_year)) &
            (model.commission_detail["accelerator_topup"] > 0)
        ]
        total_commission = round(float(det_all["accelerator_topup"].sum()), 2)

    emp["annual_target_eur"]     = annual_target_eur
    emp["annual_attainment_pct"] = att_pct
    emp["ytd_acv_eur"]           = round(ytd_acv, 2)
    emp["year_end_commission"]   = total_commission

    return {
        "employee":        emp,
        "quarters":        quarters_out,
        "year_end":        year_end,
        "all_accelerators": all_accelerators,
        "year":            year,
    }


# ---------------------------------------------------------------------------
# AE Monthly breakdown: per-AE monthly ACV for the full year
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
            "employee_id":        str(emp_id),
            "name":               emp["name"],
            "currency":           currency,
            "region":             emp["region"],
            "q_target_eur":       q_target_eur,
            "monthly_acv_eur":    monthly_acv_eur,
            "monthly_acv_my_eur": monthly_acv_my_eur,
        })

    return {
        "months":       month_keys,
        "month_labels": month_labels,
        "employees":    employees_out,
        "year":         year,
    }
