"""Account Manager (AM) commission plan — FY26.

Annual bonus: 20% of base salary, prorated and paid quarterly.

Single measure:
  NRR — 100% weight  (same quarterly tier structure as CSA plan)

NRR Accelerator: +2% of bonus per 1% above NRR target; paid at year-end (Q4).

Multi-year ACV commission: 1% on year-2+ ACV from multi-year renewal deals in
the AM's book of business. Booked at the deal's close-date month.
Note: break-clause data is not in InputData; break-clause adjustments should
be applied manually via SPIF.

Referral commissions (same rates as CSA):
  Active referral (outbound): EUR 115 / GBP 100 / SEK 1,300 per SAO + 5% ACV CW
  Inbound referral:           EUR  55 / GBP  47 / SEK   590 per SAO + 1% ACV CW

One-off services (Professional Services): 50% of Non-Recurring TCV included
in the NRR numerator -- same as CS plan, no separate payment.
"""

import pandas as pd

from src.commission_plans.cs import (
    CSACommissionPlan,
    REFERRAL_RATES,
    REFERRAL_CW_RATES,
    NRR_ACCELERATOR_PER_PCT,
)
from src.helpers import get_fx_rate, quarter_months, quarter_end_month

ANNUAL_BONUS_PCT    = 0.20
MULTI_YEAR_ACV_RATE = 0.01
NRR_WEIGHT          = 1.0  # 100% of bonus


class AMCommissionPlan(CSACommissionPlan):
    role = "am"

    def get_rates(self, currency: str) -> dict:
        return REFERRAL_RATES.get(currency, REFERRAL_RATES["EUR"])

    def get_components(self) -> list[str]:
        return [
            "nrr_pct",
            "nrr_bonus",
            "quarterly_bonus_target",
            "multi_year_comm",
            "referral_sao_count",
            "referral_sao_comm",
            "referral_cw_comm",
            "accelerator_topup",
            "total_commission",
        ]

    # ------------------------------------------------------------------
    # Monthly commission
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
        rates    = self.get_rates(currency)

        # ---- Referral commissions — paid at quarter-end ----
        referral_sao_count = 0
        referral_sao_comm  = 0.0
        referral_cw_comm   = 0.0

        if month.month in (3, 6, 9, 12) and cs_performance:
            ref_df = cs_performance.get("referrals", pd.DataFrame())
            if not ref_df.empty:
                quarter = (month.month - 1) // 3 + 1
                q_start = pd.Timestamp(year=month.year, month=(quarter - 1) * 3 + 1, day=1)

                sao_rows = ref_df[
                    (ref_df["employee_id"] == emp_id) &
                    (ref_df["month"] >= q_start) &
                    (ref_df["month"] <= month)
                ]
                for _, r in sao_rows.iterrows():
                    rtype    = str(r.get("referral_type", "")).lower()
                    rate_key = "outbound" if rtype == "outbound" else "inbound"
                    referral_sao_count += 1
                    referral_sao_comm  += rates[rate_key]

                cw_candidates = ref_df[
                    (ref_df["employee_id"] == emp_id) &
                    ref_df.get("is_closed_won", pd.Series(False, index=ref_df.index))
                ] if "is_closed_won" in ref_df.columns else pd.DataFrame()
                for _, r in cw_candidates.iterrows():
                    if r.get("is_forecast", False):
                        continue
                    cd = r.get("close_date")
                    if pd.isna(cd) or cd is None:
                        continue
                    close_month = pd.Timestamp(cd).to_period("M").to_timestamp()
                    if q_start <= close_month <= month:
                        rtype    = str(r.get("referral_type", "")).lower()
                        rate_key = "outbound" if rtype == "outbound" else "inbound"
                        acv_eur  = float(r.get("acv_eur", 0))
                        referral_cw_comm += acv_eur * REFERRAL_CW_RATES[rate_key] * fx_rate

        # ---- Multi-year ACV commission (1% of year-2+ ACV on renewals) ----
        multi_year_comm = 0.0
        if cs_performance:
            my_df = cs_performance.get("am_multi_year_acv", pd.DataFrame())
            if not my_df.empty:
                my_rows = my_df[
                    (my_df["employee_id"] == emp_id) &
                    (my_df["month"] == month)
                ]
                for _, r in my_rows.iterrows():
                    multi_year_comm += float(r.get("acv_eur", 0)) * MULTI_YEAR_ACV_RATE * fx_rate
            multi_year_comm = round(multi_year_comm, 2)

        # ---- Quarterly NRR bonus — paid at quarter-end months only ----
        nrr_pct               = 0.0
        nrr_bonus             = 0.0
        quarterly_bonus_target = 0.0

        if month.month in (3, 6, 9, 12) and cs_performance:
            year    = month.year
            quarter = (month.month - 1) // 3 + 1

            sal_monthly = self._get_salary_monthly(emp_id, month, salary_history)
            quarterly_bonus_target = sal_monthly * 12 * ANNUAL_BONUS_PCT / 4

            nrr_pct, nrr_bonus = self._calc_am_nrr_bonus(
                emp_id, year, quarter, quarterly_bonus_target, cs_performance,
            )

        total = referral_sao_comm + referral_cw_comm + multi_year_comm + nrr_bonus

        return {
            "employee_id":             emp_id,
            "month":                   month,
            "currency":                currency,
            "fx_rate":                 fx_rate,
            "nrr_pct":                 round(nrr_pct, 2),
            "nrr_bonus":               round(nrr_bonus, 2),
            # Schema stubs for CS columns (keep commission_monthly consistent)
            "csat_score_pct":          0.0,
            "csat_bonus":              0.0,
            "credits_used_pct":        0.0,
            "credits_bonus":           0.0,
            "quarterly_bonus_target":  round(quarterly_bonus_target, 2),
            "multi_year_comm":         round(multi_year_comm, 2),
            "referral_sao_count":      referral_sao_count,
            "referral_sao_comm":       round(referral_sao_comm, 2),
            "referral_cw_comm":        round(referral_cw_comm, 2),
            "accelerator_topup":       0.0,
            "outbound_sao_count":      0,
            "inbound_sao_count":       0,
            "total_sao_count":         0,
            "attainment_pct":          0.0,
            "monthly_sao_target":      0,
            "total_commission":        round(total, 2),
        }

    # ------------------------------------------------------------------
    # Quarterly NRR accelerator — Q4 year-end only
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
        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        q_months = quarter_months(year, quarter)
        q_end    = quarter_end_month(q_months[0])

        accelerator_topup = 0.0

        if quarter == 4 and cs_performance:
            nrr_df = cs_performance.get("am_nrr", pd.DataFrame())
            if not nrr_df.empty:
                row = nrr_df[
                    (nrr_df["employee_id"] == emp_id) &
                    (nrr_df["year"] == year) &
                    (nrr_df["quarter"] == quarter)
                ]
                if not row.empty:
                    nrr_pct       = float(row["nrr_pct"].iloc[0])
                    annual_target = self._get_am_nrr_target(emp_id, year, cs_performance)
                    q_nrr_target  = self._quarterly_nrr_target(annual_target, quarter)
                    if nrr_pct > q_nrr_target:
                        sal_monthly       = self._get_salary_monthly(emp_id, q_end, salary_history)
                        q_target          = sal_monthly * 12 * ANNUAL_BONUS_PCT / 4
                        nrr_portion       = q_target * NRR_WEIGHT
                        pct_above         = (nrr_pct / q_nrr_target) * 100.0 - 100.0
                        accelerator_topup = round(pct_above * NRR_ACCELERATOR_PER_PCT * nrr_portion, 2)

        return {
            "employee_id":       emp_id,
            "year":              year,
            "quarter":           quarter,
            "quarter_end_month": q_end,
            "currency":          currency,
            "accelerator_topup": accelerator_topup,
        }

    # ------------------------------------------------------------------
    # Detailed workings rows
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
        rates    = self.get_rates(currency)
        rows: list[dict] = []

        if month.month in (3, 6, 9, 12) and cs_performance:
            year    = month.year
            quarter = (month.month - 1) // 3 + 1
            rows += self._am_nrr_section_rows(emp_id, year, quarter, month, currency, cs_performance)

        rows += self._am_multi_year_section_rows(emp_id, month, currency, fx_rate, cs_performance)
        rows += self._referral_section_rows(emp_id, month, currency, fx_rate, rates, cs_performance)
        return rows

    # ------------------------------------------------------------------
    # AM-specific helpers
    # ------------------------------------------------------------------

    def _calc_am_nrr_bonus(self, emp_id, year, quarter, q_target, cs_performance):
        nrr_df = cs_performance.get("am_nrr", pd.DataFrame())
        if nrr_df.empty:
            return 0.0, 0.0
        row = nrr_df[
            (nrr_df["employee_id"] == emp_id) &
            (nrr_df["year"] == year) &
            (nrr_df["quarter"] == quarter)
        ]
        if row.empty:
            return 0.0, 0.0
        nrr_pct       = float(row["nrr_pct"].iloc[0])
        annual_target = self._get_am_nrr_target(emp_id, year, cs_performance)
        q_nrr_target  = self._quarterly_nrr_target(annual_target, quarter)
        payout_frac   = self._nrr_payout_fraction(nrr_pct, q_nrr_target, annual_target)
        nrr_bonus     = round(q_target * NRR_WEIGHT * payout_frac, 2)
        return nrr_pct, nrr_bonus

    @staticmethod
    def _get_am_nrr_target(emp_id: str, year: int, cs_performance: dict) -> float:
        targets_df = cs_performance.get("am_nrr_targets", pd.DataFrame())
        if targets_df.empty:
            return 100.0
        row = targets_df[
            (targets_df["employee_id"].astype(str) == str(emp_id)) &
            (targets_df["year"] == year)
        ]
        if row.empty or pd.isna(row["nrr_target_pct"].iloc[0]):
            return 100.0
        return float(row["nrr_target_pct"].iloc[0])

    def _am_nrr_section_rows(self, emp_id, year, quarter, month, currency, cs_performance, nrr_label="NRR"):
        nrr_df = cs_performance.get("am_nrr", pd.DataFrame())
        if nrr_df.empty:
            return []
        nrr_row = nrr_df[
            (nrr_df["employee_id"] == emp_id) &
            (nrr_df["year"] == year) &
            (nrr_df["quarter"] == quarter)
        ]
        if nrr_row.empty:
            return []

        nrr_pct       = float(nrr_row["nrr_pct"].iloc[0])
        annual_target = self._get_am_nrr_target(emp_id, year, cs_performance)
        q_nrr_target  = self._quarterly_nrr_target(annual_target, quarter)
        payout_frac   = self._nrr_payout_fraction(nrr_pct, q_nrr_target, annual_target)

        total_arr = float(nrr_row["total_arr"].iloc[0]) if "total_arr" in nrr_row.columns else 0.0
        numerator = float(nrr_row["nrr_numerator"].iloc[0]) if "nrr_numerator" in nrr_row.columns else 0.0
        net_change = numerator - total_arr

        rows = [self._section_row("NRR \u2014 100% weight", currency)]

        bkd_df = cs_performance.get("am_nrr_breakdown", pd.DataFrame())
        acct_rows_list = []
        if not bkd_df.empty:
            acct_rows = bkd_df[
                (bkd_df["employee_id"] == emp_id) &
                (bkd_df["year"] == year) &
                (bkd_df["quarter"] == quarter)
            ].sort_values("base_arr", ascending=False)
            for _, ar in acct_rows.iterrows():
                add_on     = float(ar.get("add_on", 0) or 0)
                one_off    = float(ar.get("one_off", 0) or 0)
                upsell_dwn = float(ar.get("upsell_downsell", 0) or 0)
                churn      = float(ar.get("churn", 0) or 0)
                base       = float(ar.get("base_arr", 0) or 0)
                net        = add_on + one_off + upsell_dwn + churn
                parts = []
                if add_on:     parts.append(f"Add-on: {add_on:+,.0f}")
                if one_off:    parts.append(f"One-off svc (50%): {one_off:+,.0f}")
                if upsell_dwn: parts.append(f"Renewal \u0394: {upsell_dwn:+,.0f}")
                if churn:      parts.append(f"Churn: {churn:+,.0f}")
                acct_rows_list.append({
                    "type":             "CS NRR Account",
                    "date":             "",
                    "opportunity_id":   str(ar.get("account_id", "")),
                    "opportunity_name": str(ar.get("account_name", "")),
                    "document_number":  "",
                    "sao_type":         "",
                    "acv_eur":          None,
                    "fx_rate":          None,
                    "rate_desc":        (
                        f"Base ARR: {base:,.0f}  |  " + "  |  ".join(parts)
                        if parts else f"Base ARR: {base:,.0f}"
                    ),
                    "commission":       net,
                    "currency":         currency,
                    "is_forecast":      False,
                })

        rows.append({
            "type":             "CS NRR BoB",
            "date":             "",
            "opportunity_id":   "Total Book of Business",
            "opportunity_name": "Total Book of Business",
            "document_number":  "",
            "sao_type":         "",
            "acv_eur":          None,
            "fx_rate":          None,
            "rate_desc":        "Base ARR (NRR denominator)",
            "commission":       total_arr,
            "currency":         currency,
            "is_forecast":      False,
        })
        rows += acct_rows_list
        rows.append({
            "type":             "CS NRR Numerator",
            "date":             "",
            "opportunity_id":   "BoB + changes (numerator)",
            "opportunity_name": "BoB + changes (numerator)",
            "document_number":  "",
            "sao_type":         "",
            "acv_eur":          None,
            "fx_rate":          None,
            "rate_desc":        f"{total_arr:,.0f} {net_change:+,.0f} = {numerator:,.0f}",
            "commission":       numerator,
            "currency":         currency,
            "is_forecast":      False,
        })
        rows.append({
            "type":             "AM Bonus \u2014 NRR (100%)",
            "date":             month.strftime("%Y-%m-%d"),
            "opportunity_id":   f"Q{quarter} {year}",
            "opportunity_name": f"{nrr_label} {nrr_pct:.1f}%",
            "document_number":  "",
            "sao_type":         "",
            "acv_eur":          None,
            "fx_rate":          None,
            "rate_desc":        (
                f"{nrr_label} {nrr_pct:.1f}% "
                f"(Q{quarter} target: {q_nrr_target:.1f}%) \u2192 {payout_frac*100:.0f}% payout"
            ),
            "commission":       None,
            "currency":         currency,
            "is_forecast":      False,
        })
        return rows

    def _am_multi_year_section_rows(self, emp_id, month, currency, fx_rate, cs_performance):
        if not cs_performance:
            return []
        my_df = cs_performance.get("am_multi_year_acv", pd.DataFrame())
        if my_df.empty:
            return []
        my_rows = my_df[
            (my_df["employee_id"] == emp_id) &
            (my_df["month"] == month)
        ]
        if my_rows.empty:
            return []

        rows = [self._section_row("Multi-year ACV", currency)]
        for _, r in my_rows.iterrows():
            acv_eur = float(r.get("acv_eur", 0))
            comm    = round(acv_eur * MULTI_YEAR_ACV_RATE * fx_rate, 2)
            yrs     = r.get("contract_years", 0)
            rows.append({
                "type":             "Multi-year ACV (1%)",
                "date":             month.strftime("%Y-%m-%d"),
                "opportunity_id":   str(r.get("opportunity_id", "")),
                "opportunity_name": str(r.get("opportunity_name", "")),
                "document_number":  "",
                "sao_type":         "",
                "acv_eur":          acv_eur,
                "fx_rate":          fx_rate,
                "rate_desc":        f"1% of multi-yr ACV ({yrs:.1f}yr contract) \u00d7 {fx_rate:.4f}",
                "commission":       comm,
                "currency":         currency,
                "is_forecast":      False,
            })
        return rows
