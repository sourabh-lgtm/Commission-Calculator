"""5-stage data pipeline for the Commission Calculator."""

import pandas as pd
from src.loader import load_all
from src.helpers import quarter_months, quarter_end_month, month_to_quarter
from src.commission_plans import get_plan


class CommissionModel:
    def __init__(self):
        self.employees: pd.DataFrame = pd.DataFrame()
        self.sdr_activities: pd.DataFrame = pd.DataFrame()
        self.closed_won: pd.DataFrame = pd.DataFrame()
        self.fx_rates: pd.DataFrame = pd.DataFrame()
        self.commission_monthly: pd.DataFrame = pd.DataFrame()
        self.accelerators: pd.DataFrame = pd.DataFrame()
        self.commission_detail: pd.DataFrame = pd.DataFrame()
        self.active_months: list[pd.Timestamp] = []
        self.default_month: pd.Timestamp | None = None


def run_pipeline(data_dir: str) -> CommissionModel:
    model = CommissionModel()

    # ------------------------------------------------------------------
    # Stage 1: Load CSVs
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 1: Loading data...")
    data = load_all(data_dir)
    model.employees      = data["employees"]
    model.sdr_activities = data["sdr_activities"]
    model.closed_won     = data["closed_won"]
    model.fx_rates       = data["fx_rates"]

    # ------------------------------------------------------------------
    # Stage 2: Build activity calendar (all months across data)
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 2: Building activity calendar...")
    all_months = _discover_months(model)
    model.active_months = sorted(all_months)
    model.default_month = model.active_months[-1] if model.active_months else None

    # ------------------------------------------------------------------
    # Stage 3: Calculate monthly commissions
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 3: Calculating monthly commissions...")
    monthly_rows = []
    sdrs = model.employees[model.employees["role"] == "sdr"]

    for _, emp in sdrs.iterrows():
        plan = get_plan(emp["role"])
        if plan is None:
            continue
        plan_instance = plan()
        for month in model.active_months:
            # Pro-rata: skip months entirely outside the employee plan period
            if emp["plan_start_date"] and month < emp["plan_start_date"].to_period("M").to_timestamp():
                continue
            if emp["plan_end_date"] and month > emp["plan_end_date"].to_period("M").to_timestamp():
                continue
            row = plan_instance.calculate_monthly(
                emp, month,
                model.sdr_activities,
                model.closed_won,
                model.fx_rates,
            )
            monthly_rows.append(row)

    model.commission_monthly = pd.DataFrame(monthly_rows) if monthly_rows else pd.DataFrame()

    # ------------------------------------------------------------------
    # Stage 4: Calculate quarterly accelerators
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 4: Calculating quarterly accelerators...")
    accel_rows = []
    years_quarters = _discover_year_quarters(model.active_months)

    for _, emp in sdrs.iterrows():
        plan = get_plan(emp["role"])
        if plan is None:
            continue
        plan_instance = plan()
        for (year, quarter) in years_quarters:
            row = plan_instance.calculate_quarterly_accelerator(
                emp, year, quarter, model.sdr_activities
            )
            if row["accelerator_topup"] > 0:
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
    # Stage 5: Build consolidated detail table
    # ------------------------------------------------------------------
    print("[Pipeline] Stage 5: Building report tables...")
    if not model.commission_monthly.empty:
        emp_meta = model.employees[
            ["employee_id", "name", "title", "role", "region", "country", "manager_id"]
        ]
        model.commission_detail = model.commission_monthly.merge(
            emp_meta, on="employee_id", how="left"
        )
        model.commission_detail["quarter"] = model.commission_detail["month"].apply(month_to_quarter)

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
    return list(months)


def _discover_year_quarters(months: list[pd.Timestamp]) -> list[tuple[int, int]]:
    seen = set()
    for m in months:
        q = (m.month - 1) // 3 + 1
        seen.add((m.year, q))
    return sorted(seen)
