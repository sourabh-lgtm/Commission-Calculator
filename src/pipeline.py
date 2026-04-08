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
        self.fx_rates: pd.DataFrame = pd.DataFrame()
        self.commission_monthly: pd.DataFrame = pd.DataFrame()
        self.accelerators: pd.DataFrame = pd.DataFrame()
        self.commission_detail: pd.DataFrame = pd.DataFrame()
        self.spif_awards: pd.DataFrame = pd.DataFrame()
        self.active_months: list[pd.Timestamp] = []
        self.default_month: pd.Timestamp | None = None
        # CS-specific performance inputs
        # Keys: "nrr", "csat_sent", "csat_scores", "credits", "referrals"
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
    model.fx_rates       = data["fx_rates"]
    model.cs_performance = _load_cs_performance(data_dir, data.get("employees"))

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
            row = plan.calculate_quarterly_accelerator(
                emp, year, quarter,
                model.sdr_activities,
                model.salary_history,
                cs_performance=model.cs_performance,
            )
            if row.get("accelerator_topup", 0) > 0:
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
    # Include months from CS referral dates so CS employees appear even if no SDR data
    ref_df = model.cs_performance.get("referrals", pd.DataFrame())
    if not ref_df.empty and "month" in ref_df.columns:
        months.update(ref_df["month"].dropna().unique())
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

    cs_emps = employees_df[employees_df["role"] == "cs"][["employee_id", "name"]].copy()
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

    cs_emps = employees_df[employees_df["role"] == "cs"][["employee_id", "name"]].copy()
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

    Returns DataFrame with: employee_id, year, quarter, credits_used_pct.
    """
    report_path = os.path.join(data_dir, "cs_credits_report.csv")

    if not os.path.exists(report_path):
        print("[Pipeline] CS: cs_credits_report.csv not found — skipping credits.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "credits_used_pct"])

    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            raw = pd.read_csv(report_path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        print("[Pipeline] CS: cannot decode cs_credits_report.csv — skipping.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "credits_used_pct"])

    raw.columns = raw.columns.str.strip()
    required = {"Contract Year End Date", "Credits Allocated",
                "Credits Used in Contract Year", "Account: CSA: Full Name"}
    if not required.issubset(raw.columns):
        missing = required - set(raw.columns)
        print(f"[Pipeline] CS: cs_credits_report.csv missing columns {missing} — skipping.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "credits_used_pct"])

    raw["_end_date"]  = pd.to_datetime(raw["Contract Year End Date"], format="%d/%m/%Y", errors="coerce")
    raw["_allocated"] = pd.to_numeric(raw["Credits Allocated"], errors="coerce").fillna(0)
    raw["_used"]      = pd.to_numeric(raw["Credits Used in Contract Year"], errors="coerce").fillna(0)
    raw["_csa"]       = raw["Account: CSA: Full Name"].astype(str).str.strip()
    raw = raw.dropna(subset=["_end_date"])

    raw["_year"]    = raw["_end_date"].dt.year
    raw["_quarter"] = ((raw["_end_date"].dt.month - 1) // 3 + 1)

    # ---- Build name → employee_id map (exact + last-name fallback) ----
    if employees_df is None or employees_df.empty:
        print("[Pipeline] CS: no employees_df for credits name matching.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "credits_used_pct"])

    cs_emps = employees_df[employees_df["role"] == "cs"][["employee_id", "name"]].copy()
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
    result = agg.rename(columns={
        "_employee_id": "employee_id",
        "_year":        "year",
        "_quarter":     "quarter",
    })[["employee_id", "year", "quarter", "credits_used_pct"]]

    for col in ("year", "quarter"):
        result[col] = result[col].astype("Int64")

    print(f"[Pipeline] CS: loaded credits from cs_credits_report.csv — {len(result)} employee-quarter rows.")
    return result


def _load_cs_performance(data_dir: str, employees_df: pd.DataFrame | None = None) -> dict:
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

    # ---- NRR: computed from cs_book_of_business.csv + InputData.csv ----
    from src.cs_nrr_loader import compute_cs_nrr
    print("[Pipeline] CS: computing NRR from Book of Business + InputData...")
    nrr, nrr_breakdown = compute_cs_nrr(data_dir, employees_df if employees_df is not None else pd.DataFrame())
    csat_sent   = _load_csat_sent(data_dir, employees_df)
    csat_scores = _load_csat_scores(data_dir, employees_df)
    credits    = _load_credits(data_dir, employees_df)
    referrals    = _read("cs_referrals.csv",    parse_dates=["date"])
    nrr_targets  = _read("cs_nrr_targets.csv")

    # Add month column to referrals (first of the month from date)
    if not referrals.empty and "date" in referrals.columns:
        referrals["month"] = referrals["date"].dt.to_period("M").dt.to_timestamp()

    # Normalise year/quarter columns
    for df in (nrr,):
        if not df.empty:
            for col in ("year", "quarter"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Normalise nrr_targets
    if not nrr_targets.empty:
        nrr_targets["year"]           = pd.to_numeric(nrr_targets["year"],           errors="coerce").astype("Int64")
        nrr_targets["nrr_target_pct"] = pd.to_numeric(nrr_targets["nrr_target_pct"], errors="coerce")

    return {
        "nrr":           nrr,
        "nrr_breakdown": nrr_breakdown,
        "nrr_targets":   nrr_targets,
        "csat_sent":     csat_sent,
        "csat_scores":   csat_scores,
        "credits":       credits,
        "referrals":     referrals,
    }


def _discover_year_quarters(months: list[pd.Timestamp]) -> list[tuple[int, int]]:
    seen = set()
    for m in months:
        q = (m.month - 1) // 3 + 1
        seen.add((m.year, q))
    return sorted(seen)
