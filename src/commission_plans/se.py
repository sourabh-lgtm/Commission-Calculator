"""Solutions Engineer (SE) commission plan — FY26.

Annual bonus: 20% of base salary, paid quarterly.

Two company-level measures:
  Measure 1 — Global New Business ACV  (80% weight)
  Measure 2 — Company Closing ARR      (20% weight)

Both measures share the same six-tier payout table:
  < 50%        →  0%
  50–69.99%    → 50%
  70–84.99%    → 75%
  85–99.99%    → 90%
  100–110%     → 100%
  > 110%       → 125%

Quarterly targets (from signed FY26 contract):
  Q1: NB €568k / ARR €11.116m
  Q2: NB €590k / ARR €11.825m
  Q3: NB €641k / ARR €12.464m
  Q4: NB €748k / ARR €13.240m

Data sources:
  Targets : data/se_targets.csv          (year, quarter, new_business_target_eur, arr_target_eur)
  Actuals : data/se_actual_performance.csv  (year, quarter, new_business_acv_eur, company_arr_eur)
  Finance fills in actuals each quarter.
"""

import pandas as pd

from src.commission_plans.base import BaseCommissionPlan
from src.helpers import get_fx_rate, quarter_months, quarter_end_month

ANNUAL_BONUS_PCT = 0.20
NB_WEIGHT        = 0.80   # Measure 1: Global New Business
ARR_WEIGHT       = 0.20   # Measure 2: Company ARR


def _tier_payout(achievement_pct: float) -> float:
    """Return the bonus payout fraction for a given achievement percentage."""
    if achievement_pct >= 110:
        return 1.25
    if achievement_pct >= 100:
        return 1.00
    if achievement_pct >= 85:
        return 0.90
    if achievement_pct >= 70:
        return 0.75
    if achievement_pct >= 50:
        return 0.50
    return 0.00


def _tier_label(achievement_pct: float) -> str:
    if achievement_pct >= 110:
        return "> 110% \u2192 125% payout"
    if achievement_pct >= 100:
        return "100\u2013110% \u2192 100% payout"
    if achievement_pct >= 85:
        return "85\u201399.99% \u2192 90% payout"
    if achievement_pct >= 70:
        return "70\u201384.99% \u2192 75% payout"
    if achievement_pct >= 50:
        return "50\u201369.99% \u2192 50% payout"
    return "< 50% \u2192 0% payout"


class SECommissionPlan(BaseCommissionPlan):
    role = "se"

    def get_rates(self, currency: str) -> dict:
        return {
            "annual_bonus_pct": ANNUAL_BONUS_PCT,
            "nb_weight":        NB_WEIGHT,
            "arr_weight":       ARR_WEIGHT,
        }

    def get_components(self) -> list[str]:
        return [
            "nb_achievement_pct",
            "nb_bonus",
            "arr_achievement_pct",
            "arr_bonus",
            "quarterly_bonus_target",
            "total_commission",
        ]

    # ------------------------------------------------------------------
    # Monthly commission — bonus booked only at quarter-end months
    # ------------------------------------------------------------------

    def calculate_monthly(
        self,
        employee: pd.Series,
        month: pd.Timestamp,
        activities: pd.DataFrame,
        closed_won: pd.DataFrame,
        fx_df: pd.DataFrame,
        salary_history: pd.DataFrame = None,
        cs_performance: dict = None,
    ) -> dict:
        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        fx_rate  = get_fx_rate(fx_df, month, currency)

        nb_achievement_pct  = 0.0
        nb_bonus            = 0.0
        arr_achievement_pct = 0.0
        arr_bonus           = 0.0
        quarterly_bonus_target = 0.0

        if month.month in (3, 6, 9, 12) and cs_performance:
            year    = month.year
            quarter = (month.month - 1) // 3 + 1

            sal_monthly = self._get_salary_monthly(emp_id, month, salary_history)
            quarterly_bonus_target = sal_monthly * 12 * ANNUAL_BONUS_PCT / 4

            targets = cs_performance.get("se_targets", pd.DataFrame())
            actual  = cs_performance.get("se_actual",  pd.DataFrame())

            nb_target = 0.0
            arr_target = 0.0
            if not targets.empty:
                t_row = targets[
                    (targets["year"].astype(int) == year) &
                    (targets["quarter"].astype(int) == quarter)
                ]
                if not t_row.empty:
                    nb_target  = float(t_row["new_business_target_eur"].iloc[0])
                    arr_target = float(t_row["arr_target_eur"].iloc[0])

            nb_actual  = 0.0
            arr_actual = 0.0
            if not actual.empty:
                a_row = actual[
                    (actual["year"].astype(int) == year) &
                    (actual["quarter"].astype(int) == quarter)
                ]
                if not a_row.empty:
                    nb_actual  = float(a_row["new_business_acv_eur"].iloc[0])
                    arr_actual = float(a_row["company_arr_eur"].iloc[0])

            if nb_target > 0:
                nb_achievement_pct = round(nb_actual / nb_target * 100, 2)
                nb_frac = _tier_payout(nb_achievement_pct)
                nb_bonus = round(quarterly_bonus_target * NB_WEIGHT * nb_frac, 2)

            if arr_target > 0:
                arr_achievement_pct = round(arr_actual / arr_target * 100, 2)
                arr_frac = _tier_payout(arr_achievement_pct)
                arr_bonus = round(quarterly_bonus_target * ARR_WEIGHT * arr_frac, 2)

        total = round(nb_bonus + arr_bonus, 2)

        return {
            "employee_id":             emp_id,
            "month":                   month,
            "currency":                currency,
            "fx_rate":                 fx_rate,
            "nb_achievement_pct":      nb_achievement_pct,
            "nb_bonus":                nb_bonus,
            "arr_achievement_pct":     arr_achievement_pct,
            "arr_bonus":               arr_bonus,
            "quarterly_bonus_target":  round(quarterly_bonus_target, 2),
            # Schema stubs to keep commission_monthly schema consistent
            "nrr_pct":                 0.0,
            "nrr_bonus":               0.0,
            "csat_score_pct":          0.0,
            "csat_bonus":              0.0,
            "credits_used_pct":        0.0,
            "credits_bonus":           0.0,
            "multi_year_comm":         0.0,
            "referral_sao_count":      0,
            "referral_sao_comm":       0.0,
            "referral_cw_comm":        0.0,
            "accelerator_topup":       0.0,
            "outbound_sao_count":      0,
            "inbound_sao_count":       0,
            "total_sao_count":         0,
            "attainment_pct":          0.0,
            "monthly_sao_target":      0,
            "total_commission":        total,
        }

    # ------------------------------------------------------------------
    # Quarterly accelerator — not used; bonus fully in calculate_monthly
    # ------------------------------------------------------------------

    def calculate_quarterly_accelerator(
        self,
        employee: pd.Series,
        year: int,
        quarter: int,
        activities: pd.DataFrame,
        salary_history: pd.DataFrame = None,
        cs_performance: dict = None,
    ) -> dict:
        months = quarter_months(year, quarter)
        q_end  = quarter_end_month(months[0])
        return {
            "employee_id":       employee["employee_id"],
            "year":              year,
            "quarter":           quarter,
            "quarter_end_month": q_end,
            "currency":          employee["currency"],
            "accelerator_topup": 0.0,
        }

    # ------------------------------------------------------------------
    # Workings rows — detail breakdown for the workings view and PDF
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
        if month.month not in (3, 6, 9, 12) or not cs_performance:
            return []

        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        year     = month.year
        quarter  = (month.month - 1) // 3 + 1

        sal_monthly = self._get_salary_monthly(emp_id, month,
                                               cs_performance.get("salary_history"))
        quarterly_bonus_target = sal_monthly * 12 * ANNUAL_BONUS_PCT / 4

        targets = cs_performance.get("se_targets", pd.DataFrame())
        actual  = cs_performance.get("se_actual",  pd.DataFrame())

        nb_target  = arr_target  = 0.0
        nb_actual  = arr_actual  = 0.0

        if not targets.empty:
            t_row = targets[
                (targets["year"].astype(int) == year) &
                (targets["quarter"].astype(int) == quarter)
            ]
            if not t_row.empty:
                nb_target  = float(t_row["new_business_target_eur"].iloc[0])
                arr_target = float(t_row["arr_target_eur"].iloc[0])

        if not actual.empty:
            a_row = actual[
                (actual["year"].astype(int) == year) &
                (actual["quarter"].astype(int) == quarter)
            ]
            if not a_row.empty:
                nb_actual  = float(a_row["new_business_acv_eur"].iloc[0])
                arr_actual = float(a_row["company_arr_eur"].iloc[0])

        nb_achievement  = round(nb_actual / nb_target * 100, 2) if nb_target > 0 else 0.0
        arr_achievement = round(arr_actual / arr_target * 100, 2) if arr_target > 0 else 0.0

        nb_frac   = _tier_payout(nb_achievement)
        arr_frac  = _tier_payout(arr_achievement)
        nb_bonus  = round(quarterly_bonus_target * NB_WEIGHT * nb_frac, 2)
        arr_bonus = round(quarterly_bonus_target * ARR_WEIGHT * arr_frac, 2)

        def _section(label):
            return {
                "type":             "CS Section",
                "date":             "",
                "opportunity_id":   label,
                "opportunity_name": label,
                "document_number":  "",
                "sao_type":         "",
                "acv_eur":          None,
                "fx_rate":          None,
                "rate_desc":        "",
                "commission":       None,
                "currency":         currency,
                "is_forecast":      False,
            }

        def _row(row_type, label, rate_desc, commission):
            return {
                "type":             row_type,
                "date":             month.strftime("%Y-%m-%d"),
                "opportunity_id":   f"Q{quarter} {year}",
                "opportunity_name": label,
                "document_number":  "",
                "sao_type":         "",
                "acv_eur":          None,
                "fx_rate":          None,
                "rate_desc":        rate_desc,
                "commission":       commission,
                "currency":         currency,
                "is_forecast":      False,
            }

        rows = []

        # ---- Measure 1: Global New Business ----
        rows.append(_section("Measure 1: Global New Business ACV \u2014 80% weight"))
        rows.append(_row(
            "SE NB Actuals",
            f"Actual: \u20ac{nb_actual:,.0f}  |  Target: \u20ac{nb_target:,.0f}",
            f"Achievement: {nb_achievement:.1f}%  \u2192  {_tier_label(nb_achievement)}",
            None,
        ))
        rows.append(_row(
            "SE Bonus \u2014 New Business (80%)",
            f"Q{quarter} {year}  \u2014  {nb_achievement:.1f}% achievement",
            (f"Quarterly target \u20ac{quarterly_bonus_target:,.2f} \u00d7 80% \u00d7 "
             f"{nb_frac*100:.0f}% payout"),
            nb_bonus,
        ))

        # ---- Measure 2: Company ARR ----
        rows.append(_section("Measure 2: Company Closing ARR \u2014 20% weight"))
        rows.append(_row(
            "SE ARR Actuals",
            f"Actual: \u20ac{arr_actual:,.0f}  |  Target: \u20ac{arr_target:,.0f}",
            f"Achievement: {arr_achievement:.1f}%  \u2192  {_tier_label(arr_achievement)}",
            None,
        ))
        rows.append(_row(
            "SE Bonus \u2014 Company ARR (20%)",
            f"Q{quarter} {year}  \u2014  {arr_achievement:.1f}% achievement",
            (f"Quarterly target \u20ac{quarterly_bonus_target:,.2f} \u00d7 20% \u00d7 "
             f"{arr_frac*100:.0f}% payout"),
            arr_bonus,
        ))

        return rows

    # ------------------------------------------------------------------
    # Salary helper (mirrors CSACommissionPlan._get_salary_monthly)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_salary_monthly(
        emp_id: str,
        month: pd.Timestamp,
        salary_history: pd.DataFrame | None,
    ) -> float:
        if salary_history is None or salary_history.empty:
            return 0.0
        sh = salary_history[salary_history["employee_id"] == emp_id]
        eligible = sh[sh["effective_date"] <= month].sort_values("effective_date", ascending=False)
        if eligible.empty:
            return 0.0
        return float(eligible["salary_monthly"].iloc[0])
