"""CS Team Lead commission plan — FY26.

Employees: Delphine Froment (161, SEK) and Johnny McCreesh (UK22, GBP).

Annual bonus: 20% of base salary, prorated and paid quarterly.

NRR / CSAT / Service Credits are evaluated on the TEAM-AGGREGATE book of
business (all accounts belonging to the lead's direct reports plus their own
accounts, if any). The pipeline pre-computes team-aggregate rows keyed by the
lead's employee_id and appends them to the same nrr / csat_sent / csat_scores
/ credits DataFrames used by individual CSAs.

Measures & weights:
  1. NRR      — 50%  (same brackets as CSA plan)
  2. CSAT     — 35%  (same brackets; ≥10 team CSATs sent per quarter)
  3. Credits  — 15%  (same brackets)

NRR accelerator: +2% of NRR portion per 1% above target; paid at year-end (Q4).

Multi-year ACV commission: 1% on year-2+ ACV from multi-year renewal deals in
the team's book of business. Booked at the deal's close-date month.
Note: break-clause data is not in InputData; break-clause adjustments should
be applied manually via SPIF.

Referrals: identical rates to the CSA plan.
"""

import pandas as pd

from src.commission_plans.cs import (
    CSACommissionPlan,
    REFERRAL_RATES,
    REFERRAL_CW_RATES,
    MEASURE_WEIGHTS,
    NRR_TIERS,
    CSAT_MIN_SENT,
    NRR_ACCELERATOR_PER_PCT,
)
from src.helpers import get_fx_rate, quarter_months, quarter_end_month

# Override: team leads earn 20% of salary (vs 15% for CSAs)
ANNUAL_BONUS_PCT = 0.20

# 1% commission on multi-year ACV
MULTI_YEAR_ACV_RATE = 0.01


class CSLeadCommissionPlan(CSACommissionPlan):
    role = "cs_lead"

    def get_components(self) -> list[str]:
        return [
            "nrr_pct",
            "nrr_bonus",
            "csat_score_pct",
            "csat_bonus",
            "credits_used_pct",
            "credits_bonus",
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

        # ---- Referral commissions (same logic as CSA) ----
        referral_sao_count = 0
        referral_sao_comm  = 0.0
        referral_cw_comm   = 0.0

        if cs_performance:
            ref_df = cs_performance.get("referrals", pd.DataFrame())
            if not ref_df.empty:
                emp_ref = ref_df[
                    (ref_df["employee_id"] == emp_id) &
                    (ref_df["month"] == month)
                ]
                for _, r in emp_ref.iterrows():
                    rtype    = str(r.get("referral_type", "")).lower()
                    rate_key = "outbound" if rtype == "outbound" else "inbound"
                    referral_sao_count += 1
                    referral_sao_comm  += rates[rate_key]
                    if r.get("is_closed_won", False) and not r.get("is_forecast", True):
                        acv_eur = float(r.get("acv_eur", 0))
                        referral_cw_comm += acv_eur * REFERRAL_CW_RATES[rate_key] * fx_rate

        # ---- Multi-year ACV commission (1% of year-2+ ACV on renewals) ----
        multi_year_comm = 0.0
        if cs_performance:
            my_df = cs_performance.get("cs_lead_multi_year_acv", pd.DataFrame())
            if not my_df.empty:
                my_rows = my_df[
                    (my_df["employee_id"] == emp_id) &
                    (my_df["month"] == month)
                ]
                for _, r in my_rows.iterrows():
                    multi_year_comm += float(r.get("acv_eur", 0)) * MULTI_YEAR_ACV_RATE * fx_rate
            multi_year_comm = round(multi_year_comm, 2)

        # ---- Quarterly bonus — quarter-end months only (Mar / Jun / Sep / Dec) ----
        nrr_pct               = 0.0
        nrr_bonus             = 0.0
        csat_score_pct        = 0.0
        csat_bonus            = 0.0
        credits_used_pct      = 0.0
        credits_bonus         = 0.0
        quarterly_bonus_target = 0.0

        if month.month in (3, 6, 9, 12) and cs_performance:
            year    = month.year
            quarter = (month.month - 1) // 3 + 1

            sal_monthly = self._get_salary_monthly(emp_id, month, salary_history)
            quarterly_bonus_target = sal_monthly * 12 * ANNUAL_BONUS_PCT / 4

            nrr_pct, nrr_bonus = self._calc_nrr_bonus(
                emp_id, year, quarter, quarterly_bonus_target, cs_performance,
            )
            csat_score_pct, csat_bonus = self._calc_csat_bonus(
                emp_id, year, quarter, quarterly_bonus_target, cs_performance,
            )
            credits_used_pct, credits_bonus = self._calc_credits_bonus(
                emp_id, year, quarter, quarterly_bonus_target, cs_performance,
            )

        total = (
            referral_sao_comm + referral_cw_comm + multi_year_comm
            + nrr_bonus + csat_bonus + credits_bonus
        )

        return {
            "employee_id":             emp_id,
            "month":                   month,
            "currency":                currency,
            "fx_rate":                 fx_rate,
            "nrr_pct":                 round(nrr_pct, 2),
            "nrr_bonus":               round(nrr_bonus, 2),
            "csat_score_pct":          round(csat_score_pct, 2),
            "csat_bonus":              round(csat_bonus, 2),
            "credits_used_pct":        round(credits_used_pct, 2),
            "credits_bonus":           round(credits_bonus, 2),
            "quarterly_bonus_target":  round(quarterly_bonus_target, 2),
            "multi_year_comm":         round(multi_year_comm, 2),
            "referral_sao_count":      referral_sao_count,
            "referral_sao_comm":       round(referral_sao_comm, 2),
            "referral_cw_comm":        round(referral_cw_comm, 2),
            "accelerator_topup":       0.0,
            # Schema stubs to keep commission_monthly consistent
            "outbound_sao_count":      0,
            "inbound_sao_count":       0,
            "total_sao_count":         0,
            "attainment_pct":          0.0,
            "monthly_sao_target":      0,
            "total_commission":        round(total, 2),
        }

    # ------------------------------------------------------------------
    # Quarterly NRR accelerator (year-end only, uses 20% bonus rate)
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
            nrr_df = cs_performance.get("nrr", pd.DataFrame())
            if not nrr_df.empty:
                row = nrr_df[
                    (nrr_df["employee_id"] == emp_id) &
                    (nrr_df["year"] == year) &
                    (nrr_df["quarter"] == quarter)
                ]
                if not row.empty:
                    nrr_pct    = float(row["nrr_pct"].iloc[0])
                    nrr_target = self._get_nrr_target(emp_id, year, cs_performance)
                    attainment = (nrr_pct / nrr_target) * 100.0
                    if attainment > 100.0:
                        sal_monthly       = self._get_salary_monthly(emp_id, q_end, salary_history)
                        q_target          = sal_monthly * 12 * ANNUAL_BONUS_PCT / 4
                        nrr_portion       = q_target * MEASURE_WEIGHTS["nrr"]
                        pct_above         = attainment - 100.0
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
    # Workings rows
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

        # ---- Referral rows (same as CSA) ----
        if cs_performance:
            ref_df = cs_performance.get("referrals", pd.DataFrame())
            if not ref_df.empty:
                emp_ref = ref_df[
                    (ref_df["employee_id"] == emp_id) &
                    (ref_df["month"] == month)
                ]
                for _, r in emp_ref.iterrows():
                    rtype    = str(r.get("referral_type", "")).lower()
                    rate_key = "outbound" if rtype == "outbound" else "inbound"
                    sao_rate = rates[rate_key]
                    date_str = r["date"].strftime("%Y-%m-%d") if hasattr(r.get("date"), "strftime") else str(r.get("date", ""))
                    account  = str(r.get("account_name", ""))

                    rows.append({
                        "type":             "CS Referral SAO",
                        "date":             date_str,
                        "opportunity_id":   account,
                        "opportunity_name": account,
                        "document_number":  "",
                        "sao_type":         rtype,
                        "acv_eur":          None,
                        "fx_rate":          None,
                        "rate_desc":        f"{currency} {sao_rate:,} / referral",
                        "commission":       float(sao_rate),
                        "currency":         currency,
                        "is_forecast":      False,
                    })

                    if r.get("is_closed_won", False):
                        acv_eur     = float(r.get("acv_eur", 0))
                        cw_pct      = REFERRAL_CW_RATES[rate_key]
                        is_forecast = bool(r.get("is_forecast", False))
                        comm        = round(acv_eur * cw_pct * fx_rate, 2) if not is_forecast else 0.0
                        rows.append({
                            "type":             "Forecast Referral CW" if is_forecast else "Referral CW",
                            "date":             date_str,
                            "opportunity_id":   account,
                            "opportunity_name": account,
                            "document_number":  "",
                            "sao_type":         rtype,
                            "acv_eur":          acv_eur,
                            "fx_rate":          fx_rate,
                            "rate_desc":        f"{cw_pct*100:.0f}% of ACV × {fx_rate:.4f}" + (" (forecast)" if is_forecast else ""),
                            "commission":       comm,
                            "currency":         currency,
                            "is_forecast":      is_forecast,
                        })

        # ---- Multi-year ACV rows ----
        if cs_performance:
            my_df = cs_performance.get("cs_lead_multi_year_acv", pd.DataFrame())
            if not my_df.empty:
                my_rows = my_df[
                    (my_df["employee_id"] == emp_id) &
                    (my_df["month"] == month)
                ]
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
                        "rate_desc":        f"1% of multi-yr ACV ({yrs:.1f}yr contract) × {fx_rate:.4f}",
                        "commission":       comm,
                        "currency":         currency,
                        "is_forecast":      False,
                    })

        # ---- Quarterly bonus summary rows (same structure as CSA) ----
        if month.month in (3, 6, 9, 12) and cs_performance:
            year    = month.year
            quarter = (month.month - 1) // 3 + 1
            nrr_df  = cs_performance.get("nrr", pd.DataFrame())

            if not nrr_df.empty:
                nrr_row = nrr_df[
                    (nrr_df["employee_id"] == emp_id) &
                    (nrr_df["year"] == year) &
                    (nrr_df["quarter"] == quarter)
                ]
                if not nrr_row.empty:
                    nrr_pct = float(nrr_row["nrr_pct"].iloc[0])
                    rows.append({
                        "type":             "CS Bonus — NRR (50%)",
                        "date":             month.strftime("%Y-%m-%d"),
                        "opportunity_id":   f"Q{quarter} {year}",
                        "opportunity_name": f"Team NRR {nrr_pct:.1f}%",
                        "document_number":  "",
                        "sao_type":         "",
                        "acv_eur":          None,
                        "fx_rate":          None,
                        "rate_desc":        f"Team NRR {nrr_pct:.1f}% → {self._nrr_payout_fraction(nrr_pct)*100:.0f}% payout (20% salary base)",
                        "commission":       None,
                        "currency":         currency,
                        "is_forecast":      False,
                    })

                    bkd_df = cs_performance.get("nrr_breakdown", pd.DataFrame())
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
                            if add_on:    parts.append(f"Add-on: {add_on:+,.0f}")
                            if one_off:   parts.append(f"One-off svc (50%): {one_off:+,.0f}")
                            if upsell_dwn: parts.append(f"Renewal Δ: {upsell_dwn:+,.0f}")
                            if churn:     parts.append(f"Churn: {churn:+,.0f}")
                            rows.append({
                                "type":             "CS NRR Account",
                                "date":             "",
                                "opportunity_id":   str(ar.get("account_id", "")),
                                "opportunity_name": str(ar.get("account_name", "")),
                                "document_number":  "",
                                "sao_type":         "",
                                "acv_eur":          None,
                                "fx_rate":          None,
                                "rate_desc":        f"Base ARR: {base:,.0f}  |  " + "  |  ".join(parts) if parts else f"Base ARR: {base:,.0f}",
                                "commission":       net,
                                "currency":         currency,
                                "is_forecast":      False,
                            })

            csat_sent_df = cs_performance.get("csat_sent", pd.DataFrame())
            scores_df    = cs_performance.get("csat_scores", pd.DataFrame())
            if not csat_sent_df.empty:
                sent_row = csat_sent_df[
                    (csat_sent_df["employee_id"] == emp_id) &
                    (csat_sent_df["year"] == year) &
                    (csat_sent_df["quarter"] == quarter)
                ]
                csats_sent = int(sent_row["csats_sent"].iloc[0]) if not sent_row.empty else 0

                avg_score_pct = 0.0
                if not scores_df.empty:
                    q_start    = pd.Timestamp(year=year, month=(quarter - 1) * 3 + 1, day=1)
                    q_end_ts   = quarter_end_month(q_start) + pd.offsets.MonthEnd(0)
                    emp_scores = scores_df[
                        (scores_df["employee_id"] == emp_id) &
                        (scores_df["date"] >= q_start) &
                        (scores_df["date"] <= q_end_ts)
                    ]
                    if not emp_scores.empty:
                        avg_score_pct = float(emp_scores["score"].mean()) / 5.0 * 100.0

                rows.append({
                    "type":             "CS Bonus — CSAT (35%)",
                    "date":             month.strftime("%Y-%m-%d"),
                    "opportunity_id":   f"Q{quarter} {year}",
                    "opportunity_name": f"Team CSAT {avg_score_pct:.1f}% ({csats_sent} sent)",
                    "document_number":  "",
                    "sao_type":         "",
                    "acv_eur":          None,
                    "fx_rate":          None,
                    "rate_desc":        f"Team CSAT {avg_score_pct:.1f}% | sent={csats_sent} (min {CSAT_MIN_SENT})",
                    "commission":       None,
                    "currency":         currency,
                    "is_forecast":      False,
                })

            credits_df = cs_performance.get("credits", pd.DataFrame())
            if not credits_df.empty:
                cr_row = credits_df[
                    (credits_df["employee_id"] == emp_id) &
                    (credits_df["year"] == year) &
                    (credits_df["quarter"] == quarter)
                ]
                if not cr_row.empty:
                    cr_pct = float(cr_row["credits_used_pct"].iloc[0])
                    rows.append({
                        "type":             "CS Bonus — Service Credits (15%)",
                        "date":             month.strftime("%Y-%m-%d"),
                        "opportunity_id":   f"Q{quarter} {year}",
                        "opportunity_name": f"Team credits used {cr_pct:.1f}%",
                        "document_number":  "",
                        "sao_type":         "",
                        "acv_eur":          None,
                        "fx_rate":          None,
                        "rate_desc":        f"Team service credits {cr_pct:.1f}% used",
                        "commission":       None,
                        "currency":         currency,
                        "is_forecast":      False,
                    })

        return rows
