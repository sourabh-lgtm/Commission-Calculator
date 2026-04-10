"""5-stage data pipeline for the Commission Calculator."""

import os
import pandas as pd
from src.loader import load_all
from src.helpers import quarter_months, quarter_end_month, month_to_quarter
from src.commission_plans import get_plan


class CommissionModel:
    def __init__(self):
        self.employees: pd.DataFrame = pd.DataFrame()
        self.salary_history: pd.DataFrame = pd.DataFrame()
        self.sdr_activities: pd.DataFrame = pd.DataFrame()
        self.closed_won: pd.DataFrame = pd.DataFrame()
        self.ae_closed_won: pd.DataFrame = pd.DataFrame()
        self.fx_rates: pd.DataFrame = pd.DataFrame()
        self.commission_monthly: pd.DataFrame = pd.DataFrame()
        self.accelerators: pd.DataFrame = pd.DataFrame()
        self.commission_detail: pd.DataFrame = pd.DataFrame()
        self.spif_awards: pd.DataFrame = pd.DataFrame()
        self.active_months: list[pd.Timestamp] = []
        self.default_month: pd.Timestamp | None = None
        # Performance inputs shared across all commission plans.
        # Keys: "nrr", "csat_sent", "csat_scores", "credits", "referrals" (CS),
        #       "ae_closed_won", "ae_targets", "fx_rates",
        #       "sdr_closed_won", "sdr_lead_targets" (AE / SDR Lead)
        self.cs_performance: dict = {}


def run_pipeline(data_dir: str) -> CommissionModel:
    model = CommissionModel()

    # ------------------------------------------------------------------
    # Stage 1: Load data (Humaans export if present, else employees.csv)
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 1: Loading data...")
    data = load_all(data_dir)
    model.employees      = data["employees"]
    model.salary_history = data["salary_history"]
    model.sdr_activities = data["sdr_activities"]
    model.closed_won     = data["closed_won"]
    model.ae_closed_won  = data.get("ae_closed_won", pd.DataFrame())
    model.fx_rates       = data["fx_rates"]
    model.cs_performance = _load_cs_performance(data_dir, data.get("employees"), model.fx_rates)
    # Inject AE / SDR Lead data into cs_performance so commission plans can access it
    model.cs_performance["ae_closed_won"]    = model.ae_closed_won
    model.cs_performance["ae_targets"]       = data.get("ae_targets", pd.DataFrame())
    model.cs_performance["sdr_closed_won"]   = model.closed_won
    model.cs_performance["sdr_lead_targets"] = data.get("sdr_lead_targets", pd.DataFrame())
    model.cs_performance["ae_ramp_report"]   = data.get("ae_ramp_report", pd.DataFrame())
    model.cs_performance["fx_rates"]         = model.fx_rates

    # ------------------------------------------------------------------
    # Stage 2: Build activity calendar (all months present in activity data)
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 2: Building activity calendar...")
    all_months = _discover_months(model)
    model.active_months = sorted(all_months)
    model.default_month = model.active_months[-1] if model.active_months else None

    # ------------------------------------------------------------------
    # Stage 3: Calculate monthly commissions (per commission-eligible role)
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 3: Calculating monthly commissions...")
    monthly_rows = []

    # Only process roles that have a registered commission plan
    commissioned = model.employees[
        model.employees["role"].apply(lambda r: get_plan(r) is not None)
    ]

    for _, emp in commissioned.iterrows():
        plan_cls = get_plan(emp["role"])
        plan     = plan_cls()
        for month in model.active_months:
            # Pro-rata: skip months outside the employee's plan window
            if pd.notna(emp["plan_start_date"]) and month < emp["plan_start_date"].to_period("M").to_timestamp():
                continue
            if pd.notna(emp["plan_end_date"]) and month > emp["plan_end_date"].to_period("M").to_timestamp():
                continue
            row = plan.calculate_monthly(
                emp, month,
                model.sdr_activities,
                model.closed_won,
                model.fx_rates,
                model.salary_history,
                cs_performance=model.cs_performance,
            )
            monthly_rows.append(row)

    model.commission_monthly = pd.DataFrame(monthly_rows) if monthly_rows else pd.DataFrame()

    # ------------------------------------------------------------------
    # Stage 4: Calculate quarterly accelerators / bonuses
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 4: Calculating quarterly accelerators...")
    accel_rows = []
    years_quarters = _discover_year_quarters(model.active_months)

    for _, emp in commissioned.iterrows():
        plan_cls = get_plan(emp["role"])
        plan     = plan_cls()
        for (year, quarter) in years_quarters:
            # Skip quarters entirely outside the employee's plan window
            q_months = quarter_months(year, quarter)
            q_end    = quarter_end_month(q_months[0])
            if pd.notna(emp["plan_start_date"]):
                plan_start_month = emp["plan_start_date"].to_period("M").to_timestamp()
                if q_end < plan_start_month:
                    continue   # entire quarter before plan start
            if pd.notna(emp["plan_end_date"]):
                plan_end_month = emp["plan_end_date"].to_period("M").to_timestamp()
                if q_months[0] > plan_end_month:
                    continue   # entire quarter after plan end
            row = plan.calculate_quarterly_accelerator(
                emp, year, quarter,
                model.sdr_activities,
                model.salary_history,
                cs_performance=model.cs_performance,
            )
            if row.get("accelerator_topup", 0) != 0:
                accel_rows.append(row)

    model.accelerators = pd.DataFrame(accel_rows) if accel_rows else pd.DataFrame()

    # Merge accelerator top-ups into commission_monthly (booked to quarter-end month)
    if not model.commission_monthly.empty and not model.accelerators.empty:
        for _, acc in model.accelerators.iterrows():
            mask = (
                (model.commission_monthly["employee_id"] == acc["employee_id"]) &
                (model.commission_monthly["month"] == acc["quarter_end_month"])
            )
            if mask.any():
                model.commission_monthly.loc[mask, "accelerator_topup"] += acc["accelerator_topup"]
                model.commission_monthly.loc[mask, "total_commission"]  += acc["accelerator_topup"]

    # ------------------------------------------------------------------
    # Stage 5: Build consolidated commission_detail table
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 5: Building report tables...")
    if not model.commission_monthly.empty:
        emp_meta = model.employees[[
            "employee_id", "name", "title", "role", "region", "country", "manager_id"
        ]]
        model.commission_detail = model.commission_monthly.merge(
            emp_meta, on="employee_id", how="left"
        )
        model.commission_detail["quarter"] = (
            model.commission_detail["month"].apply(month_to_quarter)
        )

    # ------------------------------------------------------------------
    # Stage 6: SPIFs — calculate, merge into commission totals, rebuild detail
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 6: Calculating SPIFs...")
    from src.spif import calculate_all_spifs
    model.spif_awards = calculate_all_spifs(
        data_dir,
        model.sdr_activities,
        model.closed_won,
        model.employees,
        model.fx_rates,
    )

    if not model.spif_awards.empty:
        # Ensure spif_amount column exists
        if not model.commission_monthly.empty:
            if "spif_amount" not in model.commission_monthly.columns:
                model.commission_monthly["spif_amount"] = 0.0

        for _, spif in model.spif_awards.iterrows():
            emp_id    = spif["employee_id"]
            pay_month = spif["payment_month"]
            amount    = float(spif["amount"])
            currency  = spif["currency"]

            if not model.commission_monthly.empty:
                mask = (
                    (model.commission_monthly["employee_id"] == emp_id) &
                    (model.commission_monthly["month"] == pay_month)
                )
                if mask.any():
                    model.commission_monthly.loc[mask, "spif_amount"]     += amount
                    model.commission_monthly.loc[mask, "total_commission"] += amount
                    continue

            # No existing commission row for this employee+month (e.g. AE SPIF in April)
            # Build a minimal stub row so the SPIF appears in workings
            num_cols = (model.commission_monthly.select_dtypes(include="number").columns.tolist()
                        if not model.commission_monthly.empty else [])
            stub = {c: 0.0 for c in num_cols}
            stub.update({
                "employee_id":    emp_id,
                "month":          pay_month,
                "currency":       currency,
                "fx_rate":        1.0,
                "spif_amount":    amount,
                "total_commission": amount,
                "accelerator_topup": 0.0,
                "attainment_pct": 0.0,
                "monthly_sao_target": 0,
            })
            model.commission_monthly = pd.concat(
                [model.commission_monthly, pd.DataFrame([stub])],
                ignore_index=True,
            )

        # Rebuild commission_detail to include updated totals
        if not model.commission_monthly.empty:
            emp_meta = model.employees[[
                "employee_id", "name", "title", "role", "region", "country", "manager_id"
            ]]
            model.commission_detail = model.commission_monthly.merge(
                emp_meta, on="employee_id", how="left"
            )
            model.commission_detail["quarter"] = (
                model.commission_detail["month"].apply(month_to_quarter)
            )

    print("[Pipeline] Done.")
    return model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _discover_months(model: CommissionModel) -> list[pd.Timestamp]:
    months = set()
    if not model.sdr_activities.empty and "month" in model.sdr_activities.columns:
        months.update(model.sdr_activities["month"].dropna().unique())
    if not model.closed_won.empty and "month" in model.closed_won.columns:
        months.update(model.closed_won["month"].dropna().unique())
    # Include AE deal invoice months
    if not model.ae_closed_won.empty and "month" in model.ae_closed_won.columns:
        months.update(model.ae_closed_won["month"].dropna().unique())
    # Include months from CS referral dates so CS employees appear even if no SDR data
    ref_df = model.cs_performance.get("referrals", pd.DataFrame())
    if not ref_df.empty and "month" in ref_df.columns:
        months.update(ref_df["month"].dropna().unique())
    # Ensure quarter-end months are always present for any active quarter.
    # This guarantees AE / CSA quarterly bonuses always have a commission row to land on.
    quarter_ends = set()
    for m in months:
        qe_month = ((m.month - 1) // 3 + 1) * 3   # 3, 6, 9, or 12
        quarter_ends.add(pd.Timestamp(year=m.year, month=qe_month, day=1))
    months.update(quarter_ends)
    return list(months)


def _load_csat_sent(data_dir: str, employees_df: pd.DataFrame | None) -> pd.DataFrame:
    """Load CSAT-sent counts from cs_csat_report.csv (raw CRM survey-sent export).

    Expected columns: Subject, First Name, Last Name, Date, Assigned, Account Name
    Returns DataFrame with: employee_id, year, quarter, csats_sent (Int64).
    Multiple rows per account in the same quarter are counted individually.
    """
    report_path = os.path.join(data_dir, "cs_csat_report.csv")

    if not os.path.exists(report_path):
        print("[Pipeline] CS: cs_csat_report.csv not found — skipping CSAT sent.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "csats_sent"])

    # ---- Load the raw report ----
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            raw = pd.read_csv(report_path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        print("[Pipeline] CS: cannot decode cs_csat_report.csv — skipping.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "csats_sent"])

    raw.columns = raw.columns.str.strip()
    required = {"Date", "Assigned"}
    if not required.issubset(raw.columns):
        print(f"[Pipeline] CS: cs_csat_report.csv missing columns {required - set(raw.columns)} — skipping.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "csats_sent"])

    raw["_date"]    = pd.to_datetime(raw["Date"], format="%d/%m/%Y", errors="coerce")
    raw["_assigned"] = raw["Assigned"].astype(str).str.strip()
    raw = raw.dropna(subset=["_date"])

    # ---- Build name → employee_id map (exact + last-name fallback) ----
    if employees_df is None or employees_df.empty:
        print("[Pipeline] CS: no employees_df for CSAT report name matching.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "csats_sent"])

    cs_emps = employees_df[employees_df["role"].isin(["cs", "cs_lead", "cs_director"])][["employee_id", "name"]].copy()
    cs_emps["_lower"]     = cs_emps["name"].str.strip().str.lower()
    cs_emps["_last"]      = cs_emps["_lower"].str.split().str[-1]

    name_to_id: dict[str, str] = dict(zip(cs_emps["_lower"], cs_emps["employee_id"]))
    last_counts = cs_emps["_last"].value_counts()
    last_to_id: dict[str, str] = {
        row["_last"]: row["employee_id"]
        for _, row in cs_emps.iterrows()
        if last_counts[row["_last"]] == 1
    }

    def _resolve(name: str) -> str | None:
        lower = name.strip().lower()
        if lower in name_to_id:
            return name_to_id[lower]
        last = lower.split()[-1] if lower else ""
        return last_to_id.get(last)

    raw["_employee_id"] = raw["_assigned"].map(_resolve)

    unmatched = raw[raw["_employee_id"].isna()]["_assigned"].unique()
    for u in unmatched:
        print(f"[Pipeline] CS CSAT: '{u}' not matched to any employee — skipping rows.")

    raw = raw.dropna(subset=["_employee_id"])
    raw["_year"]    = raw["_date"].dt.year
    raw["_quarter"] = ((raw["_date"].dt.month - 1) // 3 + 1)

    # YTD cumulative: count all sends from Jan 1 through end of each quarter
    # so Q2 includes Q1 sends too (same convention as NRR).
    # Each row = one CSAT sent; multiple per account are valid.
    agg = (
        raw.groupby(["_employee_id", "_year", "_quarter"])
           .size()
           .reset_index(name="csats_sent")
           .rename(columns={"_employee_id": "employee_id", "_year": "year", "_quarter": "quarter"})
    )

    # Compute cumulative YTD counts per employee per year
    rows = []
    for (emp_id, yr), grp in agg.groupby(["employee_id", "year"]):
        grp = grp.sort_values("quarter")
        cumulative = 0
        for _, r in grp.iterrows():
            cumulative += int(r["csats_sent"])
            rows.append({"employee_id": emp_id, "year": int(yr), "quarter": int(r["quarter"]), "csats_sent": cumulative})

    if not rows:
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "csats_sent"])

    result = pd.DataFrame(rows)
    for col in ("year", "quarter", "csats_sent"):
        result[col] = result[col].astype("Int64")

    print(f"[Pipeline] CS: loaded CSAT sent from cs_csat_report.csv — {len(result)} employee-quarter rows.")
    return result


def _load_csat_scores(data_dir: str, employees_df: pd.DataFrame | None) -> pd.DataFrame:
    """Load CSAT scores from cs_csat_scores_report.csv (raw CRM survey-response export).

    Expected columns: CSA, Account, Survey Response: Created Date, Score
    Returns DataFrame with: employee_id, date (datetime), score (float).
    """
    report_path = os.path.join(data_dir, "cs_csat_scores_report.csv")

    if not os.path.exists(report_path):
        print("[Pipeline] CS: cs_csat_scores_report.csv not found — skipping CSAT scores.")
        return pd.DataFrame(columns=["employee_id", "date", "score"])

    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            raw = pd.read_csv(report_path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        print("[Pipeline] CS: cannot decode cs_csat_scores_report.csv — skipping.")
        return pd.DataFrame(columns=["employee_id", "date", "score"])

    raw.columns = raw.columns.str.strip()
    date_col = "Survey Response: Created Date"
    required = {"CSA", date_col, "Score"}
    if not required.issubset(raw.columns):
        print(f"[Pipeline] CS: cs_csat_scores_report.csv missing columns {required - set(raw.columns)} — skipping.")
        return pd.DataFrame(columns=["employee_id", "date", "score"])

    raw["_date"]  = pd.to_datetime(raw[date_col], format="%d/%m/%Y", errors="coerce")
    raw["_score"] = pd.to_numeric(raw["Score"], errors="coerce")
    raw["_csa"]   = raw["CSA"].astype(str).str.strip()
    raw = raw.dropna(subset=["_date", "_score"])

    # ---- Build name → employee_id map (exact + last-name fallback) ----
    if employees_df is None or employees_df.empty:
        print("[Pipeline] CS: no employees_df for CSAT scores name matching.")
        return pd.DataFrame(columns=["employee_id", "date", "score"])

    cs_emps = employees_df[employees_df["role"].isin(["cs", "cs_lead", "cs_director"])][["employee_id", "name"]].copy()
    cs_emps["_lower"] = cs_emps["name"].str.strip().str.lower()
    cs_emps["_last"]  = cs_emps["_lower"].str.split().str[-1]

    name_to_id: dict[str, str] = dict(zip(cs_emps["_lower"], cs_emps["employee_id"]))
    last_counts = cs_emps["_last"].value_counts()
    last_to_id: dict[str, str] = {
        row["_last"]: row["employee_id"]
        for _, row in cs_emps.iterrows()
        if last_counts[row["_last"]] == 1
    }

    def _resolve(name: str) -> str | None:
        lower = name.strip().lower()
        if lower in name_to_id:
            return name_to_id[lower]
        last = lower.split()[-1] if lower else ""
        return last_to_id.get(last)

    raw["_employee_id"] = raw["_csa"].map(_resolve)

    unmatched = raw[raw["_employee_id"].isna()]["_csa"].unique()
    for u in unmatched:
        print(f"[Pipeline] CS CSAT scores: '{u}' not matched to any employee — skipping rows.")

    raw = raw.dropna(subset=["_employee_id"])
    result = raw.rename(columns={"_employee_id": "employee_id", "_date": "date", "_score": "score"})[
        ["employee_id", "date", "score"]
    ].reset_index(drop=True)

    print(f"[Pipeline] CS: loaded CSAT scores from cs_csat_scores_report.csv — {len(result)} rows.")
    return result


def _load_credits(data_dir: str, employees_df: pd.DataFrame | None) -> pd.DataFrame:
    """Load service-credit utilisation from cs_credits_report.csv (raw CRM export).

    Expected columns:
      Contract Year End Date, Credits Allocated, Credits Used in Contract Year,
      Account: CSA: Full Name

    For each year-quarter, includes only rows whose Contract Year End Date falls
    within that quarter.  Sums Credits Allocated and Credits Used per CSA, then:
      credits_used_pct = used / allocated * 100
    If allocated == 0 for a CSA in that quarter, treats as 100% (no credits at risk).

    Returns three DataFrames:
      result      — employee_id, year, quarter, credits_used_pct
      raw_result  — employee_id, year, quarter, total_allocated, total_used
      detail_df   — employee_id, year, quarter, opportunity_name, allocated, used
    """
    report_path = os.path.join(data_dir, "cs_credits_report.csv")

    _empty_credits        = pd.DataFrame(columns=["employee_id", "year", "quarter", "credits_used_pct"])
    _empty_credits_raw    = pd.DataFrame(columns=["employee_id", "year", "quarter", "total_allocated", "total_used"])
    _empty_credits_detail = pd.DataFrame(columns=["employee_id", "year", "quarter", "opportunity_name", "allocated", "used"])

    if not os.path.exists(report_path):
        print("[Pipeline] CS: cs_credits_report.csv not found — skipping credits.")
        return _empty_credits, _empty_credits_raw, _empty_credits_detail

    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            raw = pd.read_csv(report_path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        print("[Pipeline] CS: cannot decode cs_credits_report.csv — skipping.")
        return _empty_credits, _empty_credits_raw, _empty_credits_detail

    raw.columns = raw.columns.str.strip()
    required = {"Contract Year End Date", "Credits Allocated",
                "Credits Used in Contract Year", "Account: CSA: Full Name"}
    if not required.issubset(raw.columns):
        missing = required - set(raw.columns)
        print(f"[Pipeline] CS: cs_credits_report.csv missing columns {missing} — skipping.")
        return _empty_credits, _empty_credits_raw, _empty_credits_detail

    raw["_end_date"]  = pd.to_datetime(raw["Contract Year End Date"], format="%d/%m/%Y", errors="coerce")
    raw["_allocated"] = pd.to_numeric(raw["Credits Allocated"], errors="coerce").fillna(0)
    raw["_used"]      = pd.to_numeric(raw["Credits Used in Contract Year"], errors="coerce").fillna(0)
    raw["_csa"]       = raw["Account: CSA: Full Name"].astype(str).str.strip()
    raw = raw.dropna(subset=["_end_date"])

    # ---- Exclude credit rows for churned accounts ----
    # An account is considered churned for a given credits period (year, quarter)
    # if it has a Renewal Closed Lost in InputData whose close date falls within
    # the same year-quarter as the credit's Contract Year End Date.
    # This prevents CSAs from being penalised twice: once via NRR churn, and once
    # via unused credits on an account they no longer manage.
    input_path = os.path.join(data_dir, "InputData.csv")
    # Set of (account_name_lower, year, quarter) tuples for churned accounts
    churned_acct_periods: set[tuple[str, int, int]] = set()
    if os.path.exists(input_path):
        for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                inp_churn = pd.read_csv(input_path, encoding=enc,
                                        usecols=["Account Name", "Type", "Stage", "Close Date"])
                inp_churn.columns = inp_churn.columns.str.strip()
                inp_churn["_close"] = pd.to_datetime(
                    inp_churn["Close Date"], format="%d/%m/%Y", errors="coerce"
                )
                churn_rows = inp_churn[
                    (inp_churn["Type"] == "Renewal") &
                    (inp_churn["Stage"] == "Closed Lost") &
                    inp_churn["_close"].notna()
                ].copy()
                churn_rows["_yr"]  = churn_rows["_close"].dt.year
                churn_rows["_qt"]  = ((churn_rows["_close"].dt.month - 1) // 3 + 1)
                churn_rows["_acct"] = churn_rows["Account Name"].str.strip().str.lower()
                churned_acct_periods = set(
                    zip(churn_rows["_acct"], churn_rows["_yr"], churn_rows["_qt"])
                )
                break
            except Exception:
                continue

    if churned_acct_periods:
        _DEAL_TYPES = [" - Add-On - ", " - New Business - ", " - Renewal - "]

        def _acct_prefix(opp_name: str) -> str:
            for dt in _DEAL_TYPES:
                idx = opp_name.find(dt)
                if idx > 0:
                    return opp_name[:idx].strip().lower()
            return opp_name.strip().lower()

        raw["_acct_prefix"] = raw["Opportunity: Opportunity Name"].astype(str).map(_acct_prefix)
        # We need year/quarter from the end date for period-matching; compute temporarily
        raw["_end_yr"] = raw["_end_date"].dt.year
        raw["_end_qt"] = ((raw["_end_date"].dt.month - 1) // 3 + 1)
        churned_mask = raw.apply(
            lambda r: (r["_acct_prefix"], r["_end_yr"], r["_end_qt"]) in churned_acct_periods,
            axis=1,
        )
        if churned_mask.any():
            for acct in sorted(raw[churned_mask]["_acct_prefix"].unique()):
                print(f"[Pipeline] CS credits: excluding churned account '{acct}'")
            raw = raw[~churned_mask].copy()

    raw["_year"]    = raw["_end_date"].dt.year
    raw["_quarter"] = ((raw["_end_date"].dt.month - 1) // 3 + 1)

    # ---- Build name → employee_id map (exact + last-name fallback) ----
    if employees_df is None or employees_df.empty:
        print("[Pipeline] CS: no employees_df for credits name matching.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "credits_used_pct"])

    cs_emps = employees_df[employees_df["role"].isin(["cs", "cs_lead", "cs_director"])][["employee_id", "name"]].copy()
    cs_emps["_lower"] = cs_emps["name"].str.strip().str.lower()
    cs_emps["_last"]  = cs_emps["_lower"].str.split().str[-1]

    name_to_id: dict[str, str] = dict(zip(cs_emps["_lower"], cs_emps["employee_id"]))
    last_counts = cs_emps["_last"].value_counts()
    last_to_id: dict[str, str] = {
        row["_last"]: row["employee_id"]
        for _, row in cs_emps.iterrows()
        if last_counts[row["_last"]] == 1
    }

    def _resolve(name: str) -> str | None:
        lower = name.strip().lower()
        if lower in name_to_id:
            return name_to_id[lower]
        last = lower.split()[-1] if lower else ""
        return last_to_id.get(last)

    raw["_employee_id"] = raw["_csa"].map(_resolve)

    unmatched = raw[raw["_employee_id"].isna()]["_csa"].unique()
    for u in unmatched:
        print(f"[Pipeline] CS credits: '{u}' not matched to any employee — skipping rows.")

    raw = raw.dropna(subset=["_employee_id"])

    # ---- Build per-opportunity detail DataFrame ----
    if "Opportunity: Opportunity Name" in raw.columns:
        _opp_name_col = "Opportunity: Opportunity Name"
    else:
        _opp_name_col = "Credit Ledger Name" if "Credit Ledger Name" in raw.columns else None

    if _opp_name_col is not None:
        detail_df = raw[["_employee_id", "_year", "_quarter", _opp_name_col, "_allocated", "_used"]].copy()
        detail_df = detail_df.rename(columns={
            "_employee_id": "employee_id",
            "_year":        "year",
            "_quarter":     "quarter",
            _opp_name_col:  "opportunity_name",
            "_allocated":   "allocated",
            "_used":        "used",
        })
    else:
        detail_df = _empty_credits_detail.copy()

    for col in ("year", "quarter"):
        if col in detail_df.columns and not detail_df.empty:
            detail_df[col] = detail_df[col].astype("Int64")

    # ---- Aggregate per employee per year-quarter ----
    agg = (
        raw.groupby(["_employee_id", "_year", "_quarter"])
           .agg(total_allocated=("_allocated", "sum"), total_used=("_used", "sum"))
           .reset_index()
    )

    def _pct(row):
        if row["total_allocated"] == 0:
            return 100.0          # no credits committed → full payout
        return round(row["total_used"] / row["total_allocated"] * 100, 4)

    agg["credits_used_pct"] = agg.apply(_pct, axis=1)
    raw_result = agg.rename(columns={
        "_employee_id":   "employee_id",
        "_year":          "year",
        "_quarter":       "quarter",
    })[["employee_id", "year", "quarter", "total_allocated", "total_used"]]

    result = raw_result[["employee_id", "year", "quarter"]].copy()
    result["credits_used_pct"] = agg["credits_used_pct"].values

    for col in ("year", "quarter"):
        result[col]     = result[col].astype("Int64")
        raw_result[col] = raw_result[col].astype("Int64")

    print(f"[Pipeline] CS: loaded credits from cs_credits_report.csv — {len(result)} employee-quarter rows.")
    return result, raw_result, detail_df


def _load_cs_performance(data_dir: str, employees_df: pd.DataFrame | None = None, fx_df: pd.DataFrame | None = None) -> dict:
    """Load CS performance CSVs. Returns empty DataFrames for any missing file.

    NRR is computed dynamically from cs_book_of_business.csv + InputData.csv.
    CSAT sent is loaded from cs_csat_report.csv.
    """

    def _read(filename: str, parse_dates=None) -> pd.DataFrame:
        path = os.path.join(data_dir, filename)
        if not os.path.exists(path):
            print(f"[Pipeline] CS: {filename} not found — skipping.")
            return pd.DataFrame()
        df = pd.read_csv(path)
        df.columns = df.columns.str.strip()
        if parse_dates:
            for col in parse_dates:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
        if "employee_id" in df.columns:
            df["employee_id"] = df["employee_id"].astype(str).str.strip()
        return df

    from src.cs_nrr_loader import (
        compute_cs_nrr, compute_cs_lead_nrr, compute_cs_lead_multi_year_acv,
        compute_cs_director_nrr, compute_cs_director_multi_year_acv,
    )
    employees_safe = employees_df if employees_df is not None else pd.DataFrame()

    # ---- NRR: individual CSAs ----
    print("[Pipeline] CS: computing NRR from Book of Business + InputData...")
    nrr, nrr_breakdown = compute_cs_nrr(data_dir, employees_safe)

    # ---- NRR: team lead aggregates ----
    print("[Pipeline] CS: computing team-lead aggregate NRR...")
    lead_nrr, lead_nrr_bkd = compute_cs_lead_nrr(data_dir, employees_safe)
    if not lead_nrr.empty:
        nrr = pd.concat([nrr, lead_nrr], ignore_index=True)
    if not lead_nrr_bkd.empty:
        nrr_breakdown = pd.concat([nrr_breakdown, lead_nrr_bkd], ignore_index=True)

    # ---- Multi-year ACV for team leads ----
    print("[Pipeline] CS: computing multi-year ACV for team leads...")
    cs_lead_multi_year_acv = compute_cs_lead_multi_year_acv(data_dir, employees_safe)

    # ---- NRR: director aggregate (all CSAs) ----
    print("[Pipeline] CS: computing director aggregate NRR...")
    director_nrr, director_nrr_bkd = compute_cs_director_nrr(data_dir, employees_safe)
    if not director_nrr.empty:
        nrr = pd.concat([nrr, director_nrr], ignore_index=True)
    if not director_nrr_bkd.empty:
        nrr_breakdown = pd.concat([nrr_breakdown, director_nrr_bkd], ignore_index=True)

    # ---- Multi-year ACV for director (all CS accounts) ----
    print("[Pipeline] CS: computing multi-year ACV for director...")
    director_multi_year_acv = compute_cs_director_multi_year_acv(data_dir, employees_safe)
    if not director_multi_year_acv.empty:
        cs_lead_multi_year_acv = pd.concat(
            [cs_lead_multi_year_acv, director_multi_year_acv], ignore_index=True
        )

    # ---- CSAT and credits (include cs_lead employees in name matching) ----
    csat_sent   = _load_csat_sent(data_dir, employees_safe)
    csat_scores = _load_csat_scores(data_dir, employees_safe)
    credits, credits_raw, credits_detail = _load_credits(data_dir, employees_safe)
    nrr_targets = _read("cs_nrr_targets.csv")

    # ---- Referrals: loaded from Salesforce DCT report (cs_referrals_report.csv) ----
    referrals = _parse_sf_referrals_report(
        data_dir, employees_safe, fx_df if fx_df is not None else pd.DataFrame()
    )
    if not referrals.empty:
        referrals["month"] = referrals["date"].dt.to_period("M").dt.to_timestamp()

    # ---- Team-lead + director aggregate CSAT + Credits ----
    if not employees_safe.empty:
        cs_leads     = employees_safe[employees_safe["role"] == "cs_lead"]
        cs_directors = employees_safe[employees_safe["role"] == "cs_director"]

        # Drop individual credits rows for cs_leads and cs_directors — they'll be
        # replaced by team-aggregate rows below.
        if not credits.empty:
            agg_ids = set()
            if not cs_leads.empty:
                agg_ids.update(cs_leads["employee_id"].astype(str))
            if not cs_directors.empty:
                agg_ids.update(cs_directors["employee_id"].astype(str))
            if agg_ids:
                credits = credits[~credits["employee_id"].astype(str).isin(agg_ids)].copy()

        # Director aggregation runs FIRST (before leads loop) to use only raw
        # individual-employee data and avoid double-counting lead aggregate rows.
        for _, director in cs_directors.iterrows():
            director_id  = director["employee_id"]
            # All individual CS employees (cs + cs_lead) plus the director
            all_cs_ids   = list(employees_safe[
                employees_safe["role"].isin(["cs", "cs_lead"])
            ]["employee_id"]) + [director_id]

            # CSAT sent: sum across all CS members
            if not csat_sent.empty:
                dir_sent = csat_sent[csat_sent["employee_id"].isin(all_cs_ids)]
                if not dir_sent.empty:
                    agg_sent = (
                        dir_sent.groupby(["year", "quarter"])["csats_sent"]
                        .sum().reset_index()
                    )
                    agg_sent["employee_id"] = director_id
                    csat_sent = pd.concat([csat_sent, agg_sent], ignore_index=True)

            # CSAT scores: pool all CS member scores under director's employee_id
            if not csat_scores.empty:
                dir_scr = csat_scores[csat_scores["employee_id"].isin(all_cs_ids)].copy()
                if not dir_scr.empty:
                    dir_scr["employee_id"] = director_id
                    csat_scores = pd.concat([csat_scores, dir_scr], ignore_index=True)

            # Credits: re-aggregate raw allocated/used across all CS members
            if not credits_raw.empty:
                dir_cr = credits_raw[credits_raw["employee_id"].isin(all_cs_ids)]
                if not dir_cr.empty:
                    agg_cr = (
                        dir_cr.groupby(["year", "quarter"])
                        .agg(total_allocated=("total_allocated", "sum"),
                             total_used=("total_used", "sum"))
                        .reset_index()
                    )
                    agg_cr["employee_id"] = director_id
                    agg_cr["credits_used_pct"] = agg_cr.apply(
                        lambda r: 100.0 if r["total_allocated"] == 0
                        else round(r["total_used"] / r["total_allocated"] * 100, 4),
                        axis=1,
                    )
                    dir_credits = agg_cr[["employee_id", "year", "quarter", "credits_used_pct"]]
                    credits = pd.concat([credits, dir_credits], ignore_index=True)

            # Credits detail: tag all CS members' detail rows with director_id
            if not credits_detail.empty:
                dir_cr_detail = credits_detail[credits_detail["employee_id"].isin(all_cs_ids)].copy()
                if not dir_cr_detail.empty:
                    dir_cr_detail["employee_id"] = director_id
                    credits_detail = pd.concat([credits_detail, dir_cr_detail], ignore_index=True)

        for _, lead in cs_leads.iterrows():
            lead_id    = lead["employee_id"]
            team_ids   = list(employees_safe[
                employees_safe["manager_id"] == lead_id
            ]["employee_id"]) + [lead_id]

            # CSAT sent: sum YTD cumulative counts across team members
            if not csat_sent.empty:
                team_sent = csat_sent[csat_sent["employee_id"].isin(team_ids)]
                if not team_sent.empty:
                    agg_sent = (
                        team_sent.groupby(["year", "quarter"])["csats_sent"]
                        .sum().reset_index()
                    )
                    agg_sent["employee_id"] = lead_id
                    csat_sent = pd.concat([csat_sent, agg_sent], ignore_index=True)

            # CSAT scores: pool all team member scores under lead's employee_id
            if not csat_scores.empty:
                team_scr = csat_scores[csat_scores["employee_id"].isin(team_ids)].copy()
                if not team_scr.empty:
                    team_scr["employee_id"] = lead_id
                    csat_scores = pd.concat([csat_scores, team_scr], ignore_index=True)

            # Credits: re-aggregate raw allocated/used across team members
            if not credits_raw.empty:
                team_cr = credits_raw[credits_raw["employee_id"].isin(team_ids)]
                if not team_cr.empty:
                    agg_cr = (
                        team_cr.groupby(["year", "quarter"])
                        .agg(total_allocated=("total_allocated", "sum"),
                             total_used=("total_used", "sum"))
                        .reset_index()
                    )
                    agg_cr["employee_id"] = lead_id
                    agg_cr["credits_used_pct"] = agg_cr.apply(
                        lambda r: 100.0 if r["total_allocated"] == 0
                        else round(r["total_used"] / r["total_allocated"] * 100, 4),
                        axis=1,
                    )
                    lead_credits = agg_cr[["employee_id", "year", "quarter", "credits_used_pct"]]
                    credits = pd.concat([credits, lead_credits], ignore_index=True)

            # Credits detail: tag team members' detail rows with lead_id
            if not credits_detail.empty:
                team_cr_detail = credits_detail[credits_detail["employee_id"].isin(team_ids)].copy()
                if not team_cr_detail.empty:
                    team_cr_detail["employee_id"] = lead_id
                    credits_detail = pd.concat([credits_detail, team_cr_detail], ignore_index=True)

    # Normalise year/quarter columns
    for df in (nrr,):
        if not df.empty:
            for col in ("year", "quarter"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    if not nrr_targets.empty:
        nrr_targets["year"]           = pd.to_numeric(nrr_targets["year"],           errors="coerce").astype("Int64")
        nrr_targets["nrr_target_pct"] = pd.to_numeric(nrr_targets["nrr_target_pct"], errors="coerce")

    return {
        "nrr":                    nrr,
        "nrr_breakdown":          nrr_breakdown,
        "nrr_targets":            nrr_targets,
        "csat_sent":              csat_sent,
        "csat_scores":            csat_scores,
        "credits":                credits,
        "credits_detail":         credits_detail,
        "referrals":              referrals,
        "cs_lead_multi_year_acv": cs_lead_multi_year_acv,
    }


def _parse_sf_referrals_report(
    data_dir: str,
    employees_df: pd.DataFrame,
    fx_df: pd.DataFrame,
) -> pd.DataFrame:
    """Parse the Salesforce DCT referral report into the referrals DataFrame schema.

    Expected file: data/cs_referrals_report.csv (Salesforce report export).
    Key columns used:
      - Company Referrer  : name of the CSA/team lead who made the referral
      - DCT Discovery     : SAO date (format 'DD/MM/YYYY, HH:MM')
      - Stage             : 'Closed Won' triggers ACV commission
      - Amount / Amount Currency : ACV, converted to EUR
      - Lead Source       : 'Outbound …' → outbound referral_type, else inbound

    A row must have a DCT Discovery date to generate a SAO commission.
    A row with Stage == 'Closed Won' additionally earns the ACV commission.
    """
    path = os.path.join(data_dir, "cs_referrals_report.csv")
    if not os.path.exists(path):
        return pd.DataFrame()

    print("[Pipeline] CS referrals: loading Salesforce DCT referral report...")
    df = pd.read_csv(path, encoding="cp1252")
    df.columns = df.columns.str.strip()

    # Only process rows that have a DCT Discovery date (these qualify for SAO commission)
    dct_col = "DCT Discovery"
    if dct_col not in df.columns:
        print(f"[Pipeline] CS referrals: '{dct_col}' column missing in cs_referrals_report.csv — skipping.")
        return pd.DataFrame()

    df = df[df[dct_col].notna() & (df[dct_col].astype(str).str.strip() != "")].copy()
    if df.empty:
        return pd.DataFrame()

    # Parse DCT Discovery date (Salesforce format: "12/09/2025, 14:20" → day/month/year)
    df["dct_date"] = pd.to_datetime(
        df[dct_col].astype(str).str.split(",").str[0].str.strip(),
        format="%d/%m/%Y",
        errors="coerce",
    )
    df = df[df["dct_date"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    # Build name → employee_id lookup across all employees
    # (AM referrals will be wired up once an AM commission plan is added)
    all_emps = employees_df.copy() if not employees_df.empty else pd.DataFrame()

    name_to_id: dict[str, str] = {}
    for _, emp in all_emps.iterrows():
        eid = str(emp["employee_id"])
        # Full name (preferred)
        full = ""
        if "name" in emp.index and pd.notna(emp["name"]):
            full = emp["name"].strip()
        elif "first_name" in emp.index and "last_name" in emp.index:
            fn = emp["first_name"].strip() if pd.notna(emp.get("first_name")) else ""
            ln = emp["last_name"].strip()  if pd.notna(emp.get("last_name"))  else ""
            full = f"{fn} {ln}".strip()
        if full:
            name_to_id[full.lower()] = eid
        # First name only (fallback for partial names in Salesforce)
        first = ""
        if "first_name" in emp.index and pd.notna(emp.get("first_name")):
            first = emp["first_name"].strip()
        elif full:
            first = full.split()[0]
        if first and first.lower() not in name_to_id:
            name_to_id[first.lower()] = eid

    rows = []
    for _, r in df.iterrows():
        referrer = str(r.get("Company Referrer", "")).strip()
        if not referrer:
            continue

        # Match referrer name → employee_id
        emp_id = name_to_id.get(referrer.lower())
        if emp_id is None:
            # Try first word of referrer (handles "Delphine" matching "Delphine Froment")
            first_word = referrer.split()[0].lower()
            emp_id = name_to_id.get(first_word)
        if emp_id is None:
            print(f"[Pipeline] CS referrals: could not match referrer '{referrer}' to any employee — skipping row.")
            continue

        dct_date = r["dct_date"]

        # Parse Close Date (format DD/MM/YYYY) — used for ACV commission quarter
        raw_close = str(r.get("Close Date", "")).strip()
        close_date = pd.to_datetime(raw_close, format="%d/%m/%Y", errors="coerce")
        if pd.isna(close_date):
            close_date = None

        currency = str(r.get("Amount Currency", "EUR")).strip() or "EUR"
        raw_amount = r.get("Amount", 0)
        amount_local = float(str(raw_amount).replace(",", "")) if pd.notna(raw_amount) else 0.0

        # Convert local currency → EUR using the DCT month's FX rate
        amount_eur = amount_local
        if currency != "EUR" and not fx_df.empty:
            col = f"EUR_{currency}"
            if col in fx_df.columns:
                dct_month = dct_date.to_period("M").to_timestamp()
                fx_row = fx_df[fx_df["month"] == dct_month]
                if fx_row.empty:
                    prior = fx_df[fx_df["month"] <= dct_month]
                    fx_row = prior.iloc[[-1]] if not prior.empty else pd.DataFrame()
                if not fx_row.empty:
                    fx_val = float(fx_row[col].iloc[0])
                    if fx_val > 0:
                        amount_eur = amount_local / fx_val   # EUR_XXX = local per EUR

        # Referral type from Lead Source
        lead_source = str(r.get("Lead Source", "")).strip()
        referral_type = "outbound" if "outbound" in lead_source.lower() else "inbound"

        # Closed-won flag
        stage = str(r.get("Stage", "")).strip()
        is_closed_won = stage.lower() == "closed won"

        rows.append({
            "employee_id":   emp_id,
            "date":          dct_date,
            "close_date":    close_date,
            "account_name":  str(r.get("Account Name", "")).strip(),
            "referral_type": referral_type,
            "acv_eur":       round(amount_eur, 2),
            "is_closed_won": is_closed_won,
            "is_forecast":   False,
        })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result["employee_id"] = result["employee_id"].astype(str)
    print(f"[Pipeline] CS referrals: loaded {len(result)} referral rows from Salesforce report ({result['is_closed_won'].sum()} closed-won).")
    return result


def _discover_year_quarters(months: list[pd.Timestamp]) -> list[tuple[int, int]]:
    seen = set()
    for m in months:
        q = (m.month - 1) // 3 + 1
        seen.add((m.year, q))
    return sorted(seen)
