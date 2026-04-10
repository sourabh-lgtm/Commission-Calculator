"""Account Executive (AE) commission plan — FY26.

Commission structure:
  - Quarterly gate: if quarterly 1st-year ACV (by close date) < 50% of quarterly target
    → that quarter earns no commission.
  - Base rate: 10% of 1st-year ACV (for qualifying quarters).
  - Multi-year bonus: +1% of ACV beyond year 1 (multi-year incremental ACV).
  - Annual Accelerator 1: 12% on incremental ACV between 100-150% of annual target.
  - Annual Accelerator 2: 15% on incremental ACV above 150% of annual target.
  - Accelerators are a year-end true-up, booked in the final quarter.

Payout timing:
  - Commission is paid at the end of each qualifying quarter (March / June / Sep / Dec).
  - Exception: if a deal closes in one quarter but is invoiced in a future quarter,
    the commission is paid in the invoice month (immediately when invoiced).
  - The quarterly gate and ACV attribution always use the deal's CLOSE DATE.
  - Annual accelerators are added in the final earning quarter (Q4 for full-year
    employees; earlier for leavers).

calculate_monthly() returns ACV pipeline data (zero commission amounts).
calculate_quarterly_accelerator() runs for EACH quarter:
  - Uses close_date to bucket deals into the quarter.
  - Applies the 50% gate.
  - Returns base + multi-year commission as accelerator_topup (booked to quarter-end).
  - At the final quarter only: also computes annual accelerator tiers.

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

# ---------------------------------------------------------------------------
# Ramp plan criteria & payout (evaluated from ae_ramp_report.csv)
# Per the commission plan contract, 5 criteria must ALL be met:
#   1. Pipeline Value ≥ €200k
#   2. Pipeline Customer Count ≥ 7 at Solutions Design stage or above
#   3. Multi-Threading: Count of opps with 2+ contacts ≥ Count of opps Solution Design+
#   4. Pipeline Stage: Solutions Design and Above (gate for criteria 2 & 3)
#   5. SAO Generation: ≥50% self-generated pipeline
# Payout: 50% of Commission = 50% × (quarterly_target × BASE_RATE)
# ---------------------------------------------------------------------------
RAMP_PIPELINE_GOAL    = 200_000  # EUR — minimum total pipeline value
RAMP_SELF_GEN_GOAL    = 0.50     # 50% — minimum self-generated (SAO generation)
RAMP_SOLUTION_DESIGN  = 7        # minimum customers at Solutions Design stage or above
RAMP_PAYOUT_PCT       = 0.50     # 50% of quarterly OTE commission if all criteria met


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
    # Quarterly pass — commission paid at the end of every qualifying quarter.
    #
    # Deal attribution uses CLOSE DATE (not invoice period) to determine
    # which quarter each deal belongs to.  The 50% quarterly gate is checked
    # against the close-date-based ACV for that quarter.
    #
    # Annual accelerator tiers are computed only in the final earning quarter
    # (Q4 for full-year employees, earlier for leavers).
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
            "employee_id":               emp_id,
            "year":                      year,
            "quarter":                   quarter,
            "quarter_end_month":         q_end,
            "currency":                  currency,
            "fx_rate":                   1.0,
            "annual_target_eur":         0.0,
            "annual_acv_first_year_eur": 0.0,
            "annual_acv_multi_year_eur": 0.0,
            "annual_attainment_pct":     0.0,
            "qualifying_acv_eur":        0.0,
            "base_commission":           0.0,
            "multi_year_commission":     0.0,
            "accelerator_1":             0.0,
            "accelerator_2":             0.0,
            "ramp_passed":               None,
            "ramp_bonus":                0.0,
            "accelerator_topup":         0.0,
        }

        # Determine the final earning quarter: Q4 by default, earlier for leavers.
        plan_end = employee.get("plan_end_date")
        final_quarter = 4
        if pd.notna(plan_end):
            plan_end_month = pd.Timestamp(plan_end).to_period("M").to_timestamp()
            for q_check in range(1, 4):  # Q1–Q3 only; Q4 is the default
                q_months_check = quarter_months(year, q_check)
                if q_months_check[0] <= plan_end_month <= q_months_check[-1]:
                    final_quarter = q_check
                    break

        # Skip quarters after the final earning quarter for this employee
        if quarter > final_quarter:
            return _zero

        # --- FX rate (quarter-end month) ---
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

        # --- AE closed-won data ---
        ae_cw = cs_performance.get("ae_closed_won", pd.DataFrame()) if cs_performance else pd.DataFrame()
        if ae_cw.empty:
            return _zero

        # Helper: is a close_date in a given list of quarter months?
        def _in_months(d, qm):
            if pd.isna(d):
                return False
            return pd.Timestamp(d).to_period("M").to_timestamp() in qm

        # --- Deals for this quarter (by close_date) ---
        q_data = ae_cw[
            (ae_cw["employee_id"] == emp_id) &
            ae_cw["close_date"].apply(lambda d: _in_months(d, months))
        ]
        # Full deal ACV (deduplicated) — used for gate check and attainment display only.
        q_deals = q_data.drop_duplicates("opportunity_id")

        if "opportunity_acv_eur" in q_deals.columns:
            q_acv_fy = float(q_deals["opportunity_acv_eur"].sum())
        else:
            q_acv_fy = float(q_data["acv_eur"].sum())

        if "opportunity_multi_year_acv_eur" in q_deals.columns:
            q_acv_my = float(q_deals["opportunity_multi_year_acv_eur"].sum())
        elif "multi_year_acv_eur" in q_data.columns:
            q_acv_my = float(q_data.drop_duplicates("opportunity_id")["multi_year_acv_eur"].sum())
        else:
            q_acv_my = 0.0

        # --- 50% gate (on full committed deal ACV) ---
        gate_met = q_acv_fy >= q_target_eur * QUARTERLY_GATE if q_target_eur > 0 else False

        # Commission is earned only on confirmed (invoiced) rows.
        # Forecast rows count toward attainment display but not toward this quarter's payout.
        if "is_forecast" in q_data.columns:
            q_confirmed = q_data[~q_data["is_forecast"]]
        else:
            q_confirmed = q_data  # no is_forecast column → treat all as confirmed

        qualifying_acv_fy = float(q_confirmed["acv_eur"].sum())          if gate_met and not q_confirmed.empty else 0.0
        qualifying_acv_my = float(q_confirmed["multi_year_acv_eur"].sum()) if gate_met and not q_confirmed.empty else 0.0

        # --- Ramp plan evaluation (Q1 only for ramp AEs) ---
        # Criteria from ae_ramp_report.csv: pipeline ≥ 200k, self-gen ≥ 50%, solution design ≥ 7
        # Payout: 50% of quarterly target (added on top of any ACV commission)
        ramp_passed = None
        ramp_bonus  = 0.0
        if is_ramp_q1 and quarter == 1:
            ramp_df  = cs_performance.get("ae_ramp_report", pd.DataFrame()) if cs_performance else pd.DataFrame()
            q_label  = f"Q{quarter}_{year}"
            if not ramp_df.empty:
                ramp_row = ramp_df[
                    (ramp_df["employee_id"].astype(str) == str(emp_id)) &
                    (ramp_df["quarter"] == q_label)
                ]
                if not ramp_row.empty:
                    r = ramp_row.iloc[0]
                    notes = str(r.get("notes", "") or "").strip().lower()
                    if "did not have ramp goals" in notes:
                        ramp_passed = None  # explicitly not on ramp plan
                    else:
                        sol_design = float(r.get("Count of opps Solution Design+", 0) or 0)
                        multi_thread = float(r.get("Count of opps with 2+ contacts", 0) or 0)
                        pipeline_ok   = float(r.get("Total Pipeline Value", 0) or 0) >= RAMP_PIPELINE_GOAL
                        self_gen_ok   = float(r.get("% of pipe self-gen", 0) or 0) >= RAMP_SELF_GEN_GOAL
                        sol_design_ok = sol_design >= RAMP_SOLUTION_DESIGN
                        # Multi-threading: at least as many multi-threaded opps as solution design opps
                        multi_thread_ok = multi_thread >= sol_design
                        ramp_passed = pipeline_ok and self_gen_ok and sol_design_ok and multi_thread_ok
                        if ramp_passed:
                            # 50% of Commission = 50% × quarterly OTE commission (target × base rate)
                            ramp_bonus = round(q_target_eur * BASE_RATE * RAMP_PAYOUT_PCT * fx_rate, 2)

        # --- Base commission for this quarter ---
        base_comm = round(qualifying_acv_fy * BASE_RATE * fx_rate, 2)
        my_comm   = round(qualifying_acv_my * MULTI_YEAR_RATE * fx_rate, 2)

        # --- Annual accelerators and full-year gate summary (final quarter only) ---
        accel_1 = 0.0
        accel_2 = 0.0
        annual_acv_fy  = q_acv_fy
        annual_acv_my  = q_acv_my
        q_gate_results: dict[int, bool] = {quarter: gate_met}

        if quarter == final_quarter:
            # Recompute full-year ACV and gate results from close_date for all quarters
            annual_acv_fy = 0.0
            annual_acv_my = 0.0
            q_gate_results = {}

            for q_check in range(1, 5):
                qm_c = quarter_months(year, q_check)
                q_data_c = ae_cw[
                    (ae_cw["employee_id"] == emp_id) &
                    ae_cw["close_date"].apply(lambda d: _in_months(d, qm_c))
                ]
                q_deals_c = q_data_c.drop_duplicates("opportunity_id")
                if "opportunity_acv_eur" in q_deals_c.columns:
                    qc_acv = float(q_deals_c["opportunity_acv_eur"].sum())
                else:
                    qc_acv = float(q_data_c["acv_eur"].sum())
                qc_gate = qc_acv >= q_target_eur * QUARTERLY_GATE if q_target_eur > 0 else False
                q_gate_results[q_check] = qc_gate
                annual_acv_fy += qc_acv
                if "opportunity_multi_year_acv_eur" in q_deals_c.columns:
                    annual_acv_my += float(q_deals_c["opportunity_multi_year_acv_eur"].sum())
                elif "multi_year_acv_eur" in q_data_c.columns:
                    annual_acv_my += float(q_data_c.drop_duplicates("opportunity_id")["multi_year_acv_eur"].sum())

            # Annual accelerators on total annual ACV (gate-independent)
            tier1_start = annual_target_eur * 1.0
            tier1_end   = annual_target_eur * 1.5

            if annual_acv_fy > tier1_start:
                tier1_acv = min(annual_acv_fy, tier1_end) - tier1_start
                accel_1 = round(tier1_acv * ACCELERATOR_1_RATE * fx_rate, 2)

            if annual_acv_fy > tier1_end:
                tier2_acv = annual_acv_fy - tier1_end
                accel_2 = round(tier2_acv * ACCELERATOR_2_RATE * fx_rate, 2)

        total_topup = round(base_comm + my_comm + accel_1 + accel_2 + ramp_bonus, 2)

        if total_topup == 0:
            return _zero

        return {
            "employee_id":               emp_id,
            "year":                      year,
            "quarter":                   quarter,
            "quarter_end_month":         q_end,
            "currency":                  currency,
            "fx_rate":                   fx_rate,
            "annual_target_eur":         annual_target_eur,
            # Per-quarter ACV (by close_date)
            "q_acv_first_year_eur":      round(q_acv_fy, 2),
            "q_acv_multi_year_eur":      round(q_acv_my, 2),
            "q_attainment_pct":          round((q_acv_fy / q_target_eur) * 100, 1) if q_target_eur > 0 else 0.0,
            "gate_met":                  gate_met,
            "qualifying_acv_eur":        round(qualifying_acv_fy, 2),
            # Annual ACV (populated at final_quarter; equals quarterly for mid-year)
            "annual_acv_first_year_eur": round(annual_acv_fy, 2),
            "annual_acv_multi_year_eur": round(annual_acv_my, 2),
            "annual_attainment_pct":     round((annual_acv_fy / annual_target_eur) * 100, 1) if annual_target_eur > 0 else 0.0,
            # Commission components
            "base_commission":           base_comm,
            "multi_year_commission":     my_comm,
            "accelerator_1":             accel_1,
            "accelerator_2":             accel_2,
            # Ramp plan (Q1 only for ramp AEs)
            "ramp_passed":               ramp_passed,
            "ramp_bonus":                ramp_bonus,
            "accelerator_topup":         total_topup,
            # Gate summary (all 4 quarters at final_quarter; just this quarter otherwise)
            "q_gate_results":            q_gate_results,
            "is_ramp_q1":                is_ramp_q1,
        }

    # ------------------------------------------------------------------
    # Deal-level workings rows.
    #
    # When quarter + year are supplied (AE quarterly view):
    #   - Filter deals by close_date falling in that quarter.
    #   - Use quarter-end month FX rate.
    #   - Show close_date as the row date.
    #
    # When only month is supplied (invoice-period view, fallback):
    #   - Filter deals by invoice month (existing behaviour).
    # ------------------------------------------------------------------
    def get_workings_rows(
        self,
        employee: pd.Series,
        month: pd.Timestamp,
        activities: pd.DataFrame,
        closed_won: pd.DataFrame,
        fx_df: pd.DataFrame,
        cs_performance: dict = None,
        quarter: int = None,
        year: int = None,
    ) -> list[dict]:
        emp_id   = employee["employee_id"]
        currency = employee["currency"]

        rows = []

        ae_cw = cs_performance.get("ae_closed_won", pd.DataFrame()) if cs_performance else pd.DataFrame()
        if ae_cw.empty:
            return rows

        if quarter is not None and year is not None:
            # Quarterly view: bucket deals by close_date, ONE ROW per opportunity
            qm = quarter_months(year, quarter)
            fx_rate = get_fx_rate(fx_df, qm[-1], currency)

            def _in_qm(d):
                if pd.isna(d):
                    return False
                return pd.Timestamp(d).to_period("M").to_timestamp() in qm

            # Show all rows (confirmed + forecast) so each invoice slot is visible.
            # Confirmed rows appear first within each deal (is_forecast=False sorts before True).
            sort_cols = (["close_date", "is_forecast"]
                         if "is_forecast" in ae_cw.columns else ["close_date"])
            emp_deals = (
                ae_cw[
                    (ae_cw["employee_id"] == emp_id) &
                    ae_cw["close_date"].apply(_in_qm)
                ]
                .sort_values(sort_cols)
            )
            date_col = "close_date"
        else:
            # Monthly / invoice-period view (fallback)
            fx_rate   = get_fx_rate(fx_df, month, currency)
            emp_deals = ae_cw[
                (ae_cw["employee_id"] == emp_id) & (ae_cw["month"] == month)
            ].sort_values("invoice_date" if "invoice_date" in ae_cw.columns else ae_cw.columns[0])
            date_col  = "invoice_date"

        for _, r in emp_deals.iterrows():
            is_forecast = bool(r.get("is_forecast", False))
            # Use the per-row (invoice-split) ACV so confirmed and forecast rows
            # each show their own share, and their commissions sum to the full deal total.
            acv_fy  = float(r["acv_eur"])
            acv_my  = float(r.get("multi_year_acv_eur", 0.0))

            raw_date = r.get(date_col)
            if raw_date is None and date_col == "close_date":
                raw_date = r.get("invoice_date")
            date_str = pd.Timestamp(raw_date).strftime("%Y-%m-%d") if pd.notna(raw_date) else ""
            doc_num  = str(r.get("document_number", "")).strip()
            opp_name = str(r.get("opportunity_name", r.get("opportunity_id", ""))).strip()
            row_type = "Forecast Deal" if is_forecast else "Closed Won"
            label    = f"10% of ACV \u00d7 {fx_rate:.4f}"
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
