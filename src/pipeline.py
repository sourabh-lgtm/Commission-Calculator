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


def _load_cs_performance(data_dir: str, employees_df: pd.DataFrame | None = None) -> dict:
    """Load CS performance CSVs. Returns empty DataFrames for any missing file.

    NRR is computed dynamically from cs_book_of_business.csv + InputData.csv
    when both files are present; otherwise falls back to the static cs_nrr.csv.
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

    # ---- NRR: compute dynamically if BoB file is present ----
    bob_path = os.path.join(data_dir, "cs_book_of_business.csv")
    if os.path.exists(bob_path) and employees_df is not None and not employees_df.empty:
        from src.cs_nrr_loader import compute_cs_nrr
        print("[Pipeline] CS: computing NRR from Book of Business + InputData...")
        nrr = compute_cs_nrr(data_dir, employees_df)
        if nrr.empty:
            nrr = _read("cs_nrr.csv")
    else:
        nrr = _read("cs_nrr.csv")
    csat_sent  = _read("cs_csat_sent.csv")
    csat_scores = _read("cs_csat_scores.csv", parse_dates=["date"])
    credits    = _read("cs_credits.csv")
    referrals    = _read("cs_referrals.csv",    parse_dates=["date"])
    nrr_targets  = _read("cs_nrr_targets.csv")

    # Add month column to referrals (first of the month from date)
    if not referrals.empty and "date" in referrals.columns:
        referrals["month"] = referrals["date"].dt.to_period("M").dt.to_timestamp()

    # Normalise year/quarter columns
    for df in (nrr, csat_sent, credits):
        if not df.empty:
            for col in ("year", "quarter"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Normalise nrr_targets
    if not nrr_targets.empty:
        nrr_targets["year"]           = pd.to_numeric(nrr_targets["year"],           errors="coerce").astype("Int64")
        nrr_targets["nrr_target_pct"] = pd.to_numeric(nrr_targets["nrr_target_pct"], errors="coerce")

    return {
        "nrr":         nrr,
        "nrr_targets": nrr_targets,
        "csat_sent":   csat_sent,
        "csat_scores": csat_scores,
        "credits":     credits,
        "referrals":   referrals,
    }


def _discover_year_quarters(months: list[pd.Timestamp]) -> list[tuple[int, int]]:
    seen = set()
    for m in months:
        q = (m.month - 1) // 3 + 1
        seen.add((m.year, q))
    return sorted(seen)
