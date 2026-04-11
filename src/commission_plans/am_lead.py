"""AM Team Lead / Director commission plan — FY26.

Inherits the individual AM plan. The only structural difference is that NRR
is evaluated on the TEAM-AGGREGATE book of business (all AM accounts pooled),
and the label in workings rows says "Team NRR".

Annual bonus: 20% of base salary, prorated and paid quarterly.
NRR accelerator: same as individual AM (+2%/1% per 1% above target, Q4 only).
Multi-year ACV: 1% on year-2+ ACV for accounts in the lead's own BoB.
Referrals: same as individual AM.
"""

import pandas as pd

from src.commission_plans.am import AMCommissionPlan


class AMLeadCommissionPlan(AMCommissionPlan):
    role = "am_lead"

    def get_workings_rows(
        self,
        employee: pd.Series,
        month: pd.Timestamp,
        activities: pd.DataFrame,
        closed_won: pd.DataFrame,
        fx_df: pd.DataFrame,
        cs_performance: dict = None,
    ) -> list[dict]:
        from src.helpers import get_fx_rate
        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        fx_rate  = get_fx_rate(fx_df, month, currency)
        rates    = self.get_rates(currency)
        rows: list[dict] = []

        if month.month in (3, 6, 9, 12) and cs_performance:
            year    = month.year
            quarter = (month.month - 1) // 3 + 1
            rows += self._am_nrr_section_rows(
                emp_id, year, quarter, month, currency, cs_performance,
                nrr_label="Team NRR",
            )

        rows += self._am_multi_year_section_rows(emp_id, month, currency, fx_rate, cs_performance)
        rows += self._referral_section_rows(emp_id, month, currency, fx_rate, rates, cs_performance)
        return rows
