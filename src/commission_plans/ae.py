"""Account Executive (AE) commission plan — FY26.

Commission structure:
  - Paid on invoicing (same timing as SDR closed-won).
  - Quarterly gate: if quarterly 1st-year ACV < 50% of quarterly target → no commission.
  - Base rate: 10% of 1st-year ACV (for qualifying quarters).
  - Multi-year bonus: +1% of ACV beyond year 1 (multi-year incremental ACV).
  - Annual Accelerator 1: 12% on incremental ACV between 100-150% of annual target.
  - Annual Accelerator 2: 15% on incremental ACV above 150% of annual target.
  - Accelerators are a year-end true-up, booked in Q4.

Commission is booked quarterly (in the quarter-end month):
  - calculate_monthly() returns ACV pipeline data with zero commission amounts.
  - calculate_quarterly_accelerator() computes all commission for the quarter,
    applies the 50% gate, and returns the total as accelerator_topup.

Per-employee targets are loaded from data/ae_targets.csv (keyed by employee_id + year).
AE closed-won data is passed via cs_performance['ae_closed_won'].
FX rates are passed via cs_performance['fx_rates'].
"""

from __future__ import annotations

import pandas as pd
from src.commission_plans.base import BaseCommissionPlan
from src.helpers import get_fx_rate, quarter_months, quarter_end_month

# ---------------------------------------------------------------------------
# Rate constants
# ---------------------------------------------------------------------------
BASE_RATE           = 0.10   # 10% of 1st-year ACV
MULTI_YEAR_RATE     = 0.01   # 1% of year-2+ ACV
ACCELERATOR_1_RATE  = 0.12   # 12% on ACV 100-150% of annual target
ACCELERATOR_2_RATE  = 0.15   # 15% on ACV above 150% of annual target
QUARTERLY_GATE      = 0.50   # 50% of quarterly target required to earn commission


class AECommissionPlan(BaseCommissionPlan):
    role = "ae"

    def get_rates(self, currency: str) -> dict:
        return {
            "base_rate":          BASE_RATE,
            "multi_year_rate":    MULTI_YEAR_RATE,
            "accelerator_1_rate": ACCELERATOR_1_RATE,
            "accelerator_2_rate": ACCELERATOR_2_RATE,
            "quarterly_gate":     QUARTERLY_GATE,
        }

    def get_components(self) -> list[str]:
        return [
            "acv_first_year_eur",
            "acv_multi_year_eur",
            "quarterly_target_eur",
            "quarterly_attainment_pct",
            "gate_met",
            "base_commission",
            "multi_year_commission",
            "accelerator_1",
            "accelerator_2",
            "accelerator_topup",
            "total_commission",
        ]

    # ------------------------------------------------------------------
    # Monthly pass — ACV data only, commission booked at quarter-end
    # ------------------------------------------------------------------
    def calculate_monthly(
        self,
        employee: pd.Series,
        month: pd.Timestamp,
        activities: pd.DataFrame,
        closed_won: pd.DataFrame,       # SDR closed_won — unused for AEs
        fx_df: pd.DataFrame,
        salary_history: pd.DataFrame = None,
        cs_performance: dict = None,
    ) -> dict:
        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        fx_rate  = get_fx_rate(fx_df, month, currency)

        # Pull AE deal data for this employee-month (from cs_performance)
        acv_fy  = 0.0
        acv_my  = 0.0
        if cs_performance:
            ae_cw = cs_performance.get("ae_closed_won", pd.DataFrame())
            if not ae_cw.empty:
                emp_month = ae_cw[
                    (ae_cw["employee_id"] == emp_id) & (ae_cw["month"] == month)
                ]
                acv_fy = float(emp_month["acv_eur"].sum())
                if "multi_year_acv_eur" in emp_month.columns:
                    acv_my = float(emp_month["multi_year_acv_eur"].sum())

        return {
            "employee_id":          emp_id,
            "month":                month,
            "currency":             currency,
            "fx_rate":              fx_rate,
            # ACV pipeline data (for display only — commission is booked quarterly)
            "acv_first_year_eur":   round(acv_fy, 2),
            "acv_multi_year_eur":   round(acv_my, 2),
            # All commission components are zero (booked at quarter-end)
            "quarterly_target_eur":      0.0,
            "quarterly_attainment_pct":  0.0,
            "gate_met":                  False,
            "base_commission":           0.0,
            "multi_year_commission":     0.0,
            "accelerator_1":             0.0,
            "accelerator_2":             0.0,
            "accelerator_topup":         0.0,
            "total_commission":          0.0,
        }

    # ------------------------------------------------------------------
    # Year-end pass — all commission paid once in Q4 (year-end true-up)
    #
    # Mirrors the CS NRR accelerator pattern: Q1–Q3 return zero; Q4 sums
    # the full year's qualifying ACV (per-quarter 50% gate still applies)
    # and adds the annual accelerator tiers on top.
    # ------------------------------------------------------------------
    def calculate_quarterly_accelerator(
        self,
        employee: pd.Series,
        year: int,
        quarter: int,
        activities: pd.DataFrame,       # unused for AEs
        salary_history: pd.DataFrame = None,
        cs_performance: dict = None,
    ) -> dict:
        emp_id   = employee["employee_id"]
        currency = employee["currency"]

        months = quarter_months(year, quarter)
        q_end  = quarter_end_month(months[0])

        _zero = {
            "employee_id":              emp_id,
            "year":                     year,
            "quarter":                  quarter,
            "quarter_end_month":        q_end,
            "currency":                 currency,
            "fx_rate":                  1.0,
            "annual_target_eur":        0.0,
            "annual_acv_first_year_eur": 0.0,
            "annual_acv_multi_year_eur": 0.0,
            "annual_attainment_pct":    0.0,
            "qualifying_acv_eur":       0.0,
            "base_commission":          0.0,
            "multi_year_commission":    0.0,
            "accelerator_1":            0.0,
            "accelerator_2":            0.0,
            "accelerator_topup":        0.0,
        }

        # Only pay at year-end (Q4)
        if quarter != 4:
            return _zero

        # --- FX rate (year-end month) ---
        fx_df   = cs_performance.get("fx_rates", pd.DataFrame()) if cs_performance else pd.DataFrame()
        fx_rate = get_fx_rate(fx_df, q_end, currency) if not fx_df.empty else 1.0
        _zero["fx_rate"] = fx_rate

        # --- Targets ---
        targets_df = cs_performance.get("ae_targets", pd.DataFrame()) if cs_performance else pd.DataFrame()
        q_target_eur      = 0.0
        annual_target_eur = 0.0
        is_ramp_q1        = False

        if not targets_df.empty:
            mask = (
                (targets_df["employee_id"].astype(str) == str(emp_id)) &
                (targets_df["year"].astype(int) == int(year))
            )
            row = targets_df[mask]
            if not row.empty:
                q_target_eur      = float(row["quarterly_target_eur"].iloc[0])
                annual_target_eur = float(row["annual_target_eur"].iloc[0])
                is_ramp_q1 = bool(row["is_ramp_q1"].iloc[0]) if "is_ramp_q1" in row.columns else False

        if annual_target_eur == 0.0:
            return _zero

        # --- Full-year AE closed-won data ---
        ae_cw = cs_performance.get("ae_closed_won", pd.DataFrame()) if cs_performance else pd.DataFrame()
        if ae_cw.empty:
            return _zero

        yr_months = []
        for q in range(1, 5):
            yr_months.extend(quarter_months(year, q))

        emp_yr = ae_cw[
            (ae_cw["employee_id"] == emp_id) &
            (ae_cw["month"].isin(yr_months))
        ]

        annual_acv_fy = float(emp_yr["acv_eur"].sum())
        annual_acv_my = float(emp_yr["multi_year_acv_eur"].sum()) if "multi_year_acv_eur" in emp_yr.columns else 0.0

        # --- Per-quarter 50% gate: sum only ACV from quarters that met the gate ---
        qualifying_acv_fy = 0.0
        qualifying_acv_my = 0.0
        q_gate_results: dict[int, bool] = {}

        for q in range(1, 5):
            qm = quarter_months(year, q)
            q_data = ae_cw[
                (ae_cw["employee_id"] == emp_id) &
                (ae_cw["month"].isin(qm))
            ]
            q_acv = float(q_data["acv_eur"].sum())

            # Ramp Q1: same gate threshold applies (targets are already set for ramp)
            gate_met = q_acv >= q_target_eur * QUARTERLY_GATE if q_target_eur > 0 else False
            q_gate_results[q] = gate_met

            if gate_met:
                qualifying_acv_fy += q_acv
                if "multi_year_acv_eur" in q_data.columns:
                    qualifying_acv_my += float(q_data["multi_year_acv_eur"].sum())

        # --- Base commission on qualifying ACV ---
        base_comm = round(qualifying_acv_fy * BASE_RATE * fx_rate, 2)
        my_comm   = round(qualifying_acv_my * MULTI_YEAR_RATE * fx_rate, 2)

        # --- Annual accelerators on total annual ACV (all quarters, no gate) ---
        accel_1 = 0.0
        accel_2 = 0.0
        tier1_start = annual_target_eur * 1.0
        tier1_end   = annual_target_eur * 1.5

        if annual_acv_fy > tier1_start:
            tier1_acv = min(annual_acv_fy, tier1_end) - tier1_start
            accel_1 = round(tier1_acv * ACCELERATOR_1_RATE * fx_rate, 2)

        if annual_acv_fy > tier1_end:
            tier2_acv = annual_acv_fy - tier1_end
            accel_2 = round(tier2_acv * ACCELERATOR_2_RATE * fx_rate, 2)

        total_topup = round(base_comm + my_comm + accel_1 + accel_2, 2)

        return {
            "employee_id":               emp_id,
            "year":                      year,
            "quarter":                   quarter,
            "quarter_end_month":         q_end,
            "currency":                  currency,
            "fx_rate":                   fx_rate,
            "annual_target_eur":         annual_target_eur,
            "annual_acv_first_year_eur": round(annual_acv_fy, 2),
            "annual_acv_multi_year_eur": round(annual_acv_my, 2),
            "annual_attainment_pct":     round((annual_acv_fy / annual_target_eur) * 100, 1),
            "qualifying_acv_eur":        round(qualifying_acv_fy, 2),
            "q_gate_results":            q_gate_results,
            "is_ramp_q1":                is_ramp_q1,
            "base_commission":           base_comm,
            "multi_year_commission":     my_comm,
            "accelerator_1":             accel_1,
            "accelerator_2":             accel_2,
            "accelerator_topup":         total_topup,
        }

    # ------------------------------------------------------------------
    # Deal-level workings rows (per invoice in the month)
    # ------------------------------------------------------------------
    def get_workings_rows(
        self,
        employee: pd.Series,
        month: pd.Timestamp,
        activities: pd.DataFrame,
        closed_won: pd.DataFrame,
        fx_df: pd.DataFrame,
        cs_performance: dict = None,
    ) -> list[dict]:
        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        fx_rate  = get_fx_rate(fx_df, month, currency)

        rows = []

        ae_cw = cs_performance.get("ae_closed_won", pd.DataFrame()) if cs_performance else pd.DataFrame()
        if ae_cw.empty:
            return rows

        emp_month = ae_cw[
            (ae_cw["employee_id"] == emp_id) & (ae_cw["month"] == month)
        ].sort_values("invoice_date" if "invoice_date" in ae_cw.columns else ae_cw.columns[0])

        for _, r in emp_month.iterrows():
            is_forecast = bool(r.get("is_forecast", False))
            acv_fy  = float(r["acv_eur"])
            acv_my  = float(r.get("multi_year_acv_eur", 0.0))

            inv_date = r.get("invoice_date")
            date_str = inv_date.strftime("%Y-%m-%d") if pd.notna(inv_date) else ""
            doc_num  = str(r.get("document_number", "")).strip()
            opp_name = str(r.get("opportunity_name", r.get("opportunity_id", ""))).strip()
            row_type = "Forecast Deal" if is_forecast else "Closed Won"
            label    = f"10% of ACV × {fx_rate:.4f}"
            if is_forecast:
                label += " (forecast)"

            rows.append({
                "type":               row_type,
                "date":               date_str,
                "opportunity_id":     r["opportunity_id"],
                "opportunity_name":   opp_name,
                "document_number":    doc_num,
                "acv_eur":            round(acv_fy, 2),
                "multi_year_acv_eur": round(acv_my, 2),
                "fx_rate":            fx_rate,
                "rate_desc":          label,
                "base_commission":    round(acv_fy * BASE_RATE * fx_rate, 2),
                "my_commission":      round(acv_my * MULTI_YEAR_RATE * fx_rate, 2),
                "currency":           currency,
                "is_forecast":        is_forecast,
                "invoicing_cadence":  str(r.get("invoicing_cadence", "")),
            })

        return rows
