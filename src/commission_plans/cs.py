"""Climate Strategy Advisor (CSA) bonus plan — FY26.

Bonus structure (quarterly, paid at quarter-end):
  Annual bonus = 15% of base salary, prorated and paid quarterly.

  Three measures:
    1. NRR  — 50% weight  (tiered payout based on NRR% vs target)
    2. CSAT — 35% weight  (tiered payout; requires ≥10 CSATs sent)
    3. Service tier credits — 15% weight (tiered payout)

  NRR Accelerator: +2% of the NRR bonus portion per 1% NRR above 100%.
  Booked via calculate_quarterly_accelerator (separate from main bonus).

Referral commissions (same rates as SDR):
  Source: data/cs_referrals.csv
  Active referral (outbound): SEK 1,300 / GBP 100 / EUR 115 per SAO + 5% ACV CW
  Inbound referral:           SEK 590  / GBP 47  / EUR 55  per SAO + 1% ACV CW
"""

import pandas as pd
from src.commission_plans.base import BaseCommissionPlan
from src.helpers import get_fx_rate, quarter_months, quarter_end_month


# ---------------------------------------------------------------------------
# Rate tables
# ---------------------------------------------------------------------------

# Referral SAO fixed amounts (per referral confirmed as SAO), local currency
REFERRAL_RATES: dict[str, dict[str, float]] = {
    "SEK": {"outbound": 1300, "inbound": 590},
    "GBP": {"outbound": 100,  "inbound": 47},
    "EUR": {"outbound": 115,  "inbound": 55},
}

# Referral closed-won ACV percentages
REFERRAL_CW_RATES: dict[str, float] = {
    "outbound": 0.05,   # 5 % of ACV
    "inbound":  0.01,   # 1 % of ACV
}

# Annual bonus as a fraction of base salary
ANNUAL_BONUS_PCT = 0.15

# Measure weightings
MEASURE_WEIGHTS: dict[str, float] = {
    "nrr":     0.50,
    "csat":    0.35,
    "credits": 0.15,
}

# CSAT minimum CSATs-sent threshold per quarter
CSAT_MIN_SENT = 10

# NRR accelerator rate: per 1% above 100%, +2% of the NRR portion
NRR_ACCELERATOR_PER_PCT = 0.02


class CSACommissionPlan(BaseCommissionPlan):
    role = "cs"

    def get_rates(self, currency: str) -> dict:
        return REFERRAL_RATES.get(currency, REFERRAL_RATES["EUR"])

    def get_components(self) -> list[str]:
        return [
            "nrr_pct",
            "nrr_bonus",
            "csat_score_pct",
            "csat_bonus",
            "credits_used_pct",
            "credits_bonus",
            "quarterly_bonus_target",
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
        activities: pd.DataFrame,       # unused (CS referrals come from cs_performance)
        closed_won: pd.DataFrame,       # unused for CS
        fx_df: pd.DataFrame,
        salary_history: pd.DataFrame = None,
        cs_performance: dict = None,
    ) -> dict:
        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        fx_rate  = get_fx_rate(fx_df, month, currency)
        rates    = self.get_rates(currency)

        # ---- Referral commissions from cs_referrals.csv ----
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

        # ---- Quarterly bonus — only at quarter-end months (Mar/Jun/Sep/Dec) ----
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

        total = referral_sao_comm + referral_cw_comm + nrr_bonus + csat_bonus + credits_bonus

        return {
            "employee_id":             emp_id,
            "month":                   month,
            "currency":                currency,
            "fx_rate":                 fx_rate,
            # Quarterly bonus components
            "nrr_pct":                 round(nrr_pct, 2),
            "nrr_bonus":               round(nrr_bonus, 2),
            "csat_score_pct":          round(csat_score_pct, 2),
            "csat_bonus":              round(csat_bonus, 2),
            "credits_used_pct":        round(credits_used_pct, 2),
            "credits_bonus":           round(credits_bonus, 2),
            "quarterly_bonus_target":  round(quarterly_bonus_target, 2),
            # Referral components
            "referral_sao_count":      referral_sao_count,
            "referral_sao_comm":       round(referral_sao_comm, 2),
            "referral_cw_comm":        round(referral_cw_comm, 2),
            # NRR accelerator is computed by the quarterly pass, not here
            "accelerator_topup":       0.0,
            # SDR-schema stub fields (keep commission_monthly schema consistent)
            "outbound_sao_count":      0,
            "inbound_sao_count":       0,
            "total_sao_count":         0,
            "attainment_pct":          0.0,
            "monthly_sao_target":      0,
            "total_commission":        round(total, 2),
        }

    # ------------------------------------------------------------------
    # Quarterly NRR accelerator
    # ------------------------------------------------------------------

    def calculate_quarterly_accelerator(
        self,
        employee: pd.Series,
        year: int,
        quarter: int,
        activities: pd.DataFrame,       # unused for CS
        salary_history: pd.DataFrame = None,
        cs_performance: dict = None,
    ) -> dict:
        """Compute NRR accelerator: +2% of NRR portion per 1% above target.

        Only paid at year-end (Q4) based on full-year cumulative NRR.
        """
        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        q_months = quarter_months(year, quarter)
        q_end    = quarter_end_month(q_months[0])

        accelerator_topup = 0.0

        # Accelerator is year-end only
        if quarter != 4:
            return {
                "employee_id":       emp_id,
                "year":              year,
                "quarter":           quarter,
                "quarter_end_month": q_end,
                "currency":          currency,
                "accelerator_topup": 0.0,
            }

        if cs_performance:
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

        # ---- Referral rows ----
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

        # ---- Quarterly bonus summary rows (quarter-end months only) ----
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
                    nrr_pct       = float(nrr_row["nrr_pct"].iloc[0])
                    annual_target = self._get_nrr_target(emp_id, year, cs_performance)
                    q_nrr_target  = self._quarterly_nrr_target(annual_target, quarter)
                    payout_frac   = self._nrr_payout_fraction(nrr_pct, q_nrr_target, annual_target)
                    rows.append({
                        "type":             "CS Bonus — NRR (50%)",
                        "date":             month.strftime("%Y-%m-%d"),
                        "opportunity_id":   f"Q{quarter} {year}",
                        "opportunity_name": f"NRR {nrr_pct:.1f}%",
                        "document_number":  "",
                        "sao_type":         "",
                        "acv_eur":          None,
                        "fx_rate":          None,
                        "rate_desc":        f"NRR {nrr_pct:.1f}% (Q{quarter} target: {q_nrr_target:.1f}%) → {payout_frac*100:.0f}% payout",
                        "commission":       None,   # shown via summary
                        "currency":         currency,
                        "is_forecast":      False,
                    })

                    # Per-account NRR breakdown sub-rows
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
                            if add_on:
                                parts.append(f"Add-on: {add_on:+,.0f}")
                            if one_off:
                                parts.append(f"One-off svc (50%): {one_off:+,.0f}")
                            if upsell_dwn:
                                parts.append(f"Renewal Δ: {upsell_dwn:+,.0f}")
                            if churn:
                                parts.append(f"Churn: {churn:+,.0f}")
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
                    q_start = pd.Timestamp(year=year, month=(quarter - 1) * 3 + 1, day=1)
                    q_end   = quarter_end_month(q_start) + pd.offsets.MonthEnd(0)
                    emp_scores = scores_df[
                        (scores_df["employee_id"] == emp_id) &
                        (scores_df["date"] >= q_start) &
                        (scores_df["date"] <= q_end)
                    ]
                    if not emp_scores.empty:
                        avg_score_pct = float(emp_scores["score"].mean()) / 5.0 * 100.0

                rows.append({
                    "type":             "CS Bonus — CSAT (35%)",
                    "date":             month.strftime("%Y-%m-%d"),
                    "opportunity_id":   f"Q{quarter} {year}",
                    "opportunity_name": f"CSAT {avg_score_pct:.1f}% ({csats_sent} sent)",
                    "document_number":  "",
                    "sao_type":         "",
                    "acv_eur":          None,
                    "fx_rate":          None,
                    "rate_desc":        f"CSAT {avg_score_pct:.1f}% | sent={csats_sent} (min {CSAT_MIN_SENT})",
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
                        "opportunity_name": f"Credits used {cr_pct:.1f}%",
                        "document_number":  "",
                        "sao_type":         "",
                        "acv_eur":          None,
                        "fx_rate":          None,
                        "rate_desc":        f"Service credits {cr_pct:.1f}% used",
                        "commission":       None,
                        "currency":         currency,
                        "is_forecast":      False,
                    })

        return rows

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_salary_monthly(
        emp_id: str,
        month: pd.Timestamp,
        salary_history: pd.DataFrame | None,
    ) -> float:
        """Return the salary_monthly in effect for this employee at `month`."""
        if salary_history is None or salary_history.empty:
            return 0.0
        sh = salary_history[salary_history["employee_id"] == emp_id]
        eligible = sh[sh["effective_date"] <= month].sort_values("effective_date", ascending=False)
        if eligible.empty:
            return 0.0
        return float(eligible["salary_monthly"].iloc[0])

    def _calc_nrr_bonus(
        self,
        emp_id: str,
        year: int,
        quarter: int,
        q_target: float,
        cs_performance: dict,
    ) -> tuple[float, float]:
        nrr_df = cs_performance.get("nrr", pd.DataFrame())
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
        annual_target = self._get_nrr_target(emp_id, year, cs_performance)
        q_nrr_target  = self._quarterly_nrr_target(annual_target, quarter)
        payout_frac   = self._nrr_payout_fraction(nrr_pct, q_nrr_target, annual_target)
        nrr_bonus     = round(q_target * MEASURE_WEIGHTS["nrr"] * payout_frac, 2)
        return nrr_pct, nrr_bonus

    @staticmethod
    def _quarterly_nrr_target(annual_target: float, quarter: int) -> float:
        """Return the quarterly NRR target using 1:1:1:2 weighting.

        Q1: 100 - loss*(1/5), Q2: *(2/5), Q3: *(3/5), Q4: *1 (= annual target).
        Returns 100.0 for all quarters when annual_target >= 100 (no loss budget).
        """
        weights = {1: 1/5, 2: 2/5, 3: 3/5, 4: 1.0}
        allowed_loss = 100.0 - annual_target
        if allowed_loss <= 0:
            return 100.0
        return 100.0 - allowed_loss * weights[quarter]

    @staticmethod
    def _get_nrr_target(emp_id: str, year: int, cs_performance: dict) -> float:
        """Return the NRR target % for this employee/year. Defaults to 100.0."""
        targets_df = cs_performance.get("nrr_targets", pd.DataFrame())
        if targets_df.empty:
            return 100.0
        row = targets_df[
            (targets_df["employee_id"].astype(str) == str(emp_id)) &
            (targets_df["year"] == year)
        ]
        if row.empty or pd.isna(row["nrr_target_pct"].iloc[0]):
            return 100.0
        return float(row["nrr_target_pct"].iloc[0])

    @staticmethod
    def _nrr_payout_fraction(nrr_pct: float, quarterly_target: float, annual_target: float) -> float:
        """Map actual NRR% to payout fraction using quarterly-prorated tier thresholds.

        Tier step = annual_target*2% prorated by how far quarterly_target is from 100%.
        When annual_target=100 (no target set) uses 2% fixed steps (original behaviour).
        """
        allowed_loss = 100.0 - annual_target
        if allowed_loss > 0:
            q_weight = (100.0 - quarterly_target) / allowed_loss
            q_step = annual_target * 0.02 * q_weight
        else:
            q_step = 2.0  # original 2%-step behaviour when no target is set
        thresholds = [
            (quarterly_target,            1.00),
            (quarterly_target - q_step,   0.90),
            (quarterly_target - 2*q_step, 0.80),
            (quarterly_target - 3*q_step, 0.70),
            (quarterly_target - 4*q_step, 0.60),
            (quarterly_target - 5*q_step, 0.50),
        ]
        for threshold, fraction in thresholds:
            if nrr_pct >= threshold:
                return fraction
        return 0.0

    def _calc_csat_bonus(
        self,
        emp_id: str,
        year: int,
        quarter: int,
        q_target: float,
        cs_performance: dict,
    ) -> tuple[float, float]:
        sent_df   = cs_performance.get("csat_sent", pd.DataFrame())
        scores_df = cs_performance.get("csat_scores", pd.DataFrame())

        # Threshold: ≥10 CSATs sent
        if sent_df.empty:
            return 0.0, 0.0
        sent_row = sent_df[
            (sent_df["employee_id"] == emp_id) &
            (sent_df["year"] == year) &
            (sent_df["quarter"] == quarter)
        ]
        if sent_row.empty or int(sent_row["csats_sent"].iloc[0]) < CSAT_MIN_SENT:
            return 0.0, 0.0

        # Average score (0–5 scale → 0–100%)
        if scores_df.empty:
            return 0.0, 0.0
        q_start    = pd.Timestamp(year=year, month=(quarter - 1) * 3 + 1, day=1)
        q_end      = quarter_end_month(q_start) + pd.offsets.MonthEnd(0)
        emp_scores = scores_df[
            (scores_df["employee_id"] == emp_id) &
            (scores_df["date"] >= q_start) &
            (scores_df["date"] <= q_end)
        ]
        if emp_scores.empty:
            return 0.0, 0.0

        csat_score_pct = float(emp_scores["score"].mean()) / 5.0 * 100.0

        if csat_score_pct < 80.0:
            payout_frac = 0.0
        elif csat_score_pct < 90.0:
            payout_frac = 0.5
        else:
            payout_frac = 1.0

        csat_bonus = round(q_target * MEASURE_WEIGHTS["csat"] * payout_frac, 2)
        return round(csat_score_pct, 2), csat_bonus

    def _calc_credits_bonus(
        self,
        emp_id: str,
        year: int,
        quarter: int,
        q_target: float,
        cs_performance: dict,
    ) -> tuple[float, float]:
        credits_df = cs_performance.get("credits", pd.DataFrame())
        if credits_df.empty:
            return 0.0, 0.0
        row = credits_df[
            (credits_df["employee_id"] == emp_id) &
            (credits_df["year"] == year) &
            (credits_df["quarter"] == quarter)
        ]
        if row.empty:
            # No credits allocated in this portfolio → full payout (100%)
            credits_bonus = round(q_target * MEASURE_WEIGHTS["credits"] * 1.0, 2)
            return 100.0, credits_bonus

        credits_used_pct = float(row["credits_used_pct"].iloc[0])

        if credits_used_pct < 50.0:
            payout_frac = 0.0
        elif credits_used_pct < 75.0:
            payout_frac = 0.5
        elif credits_used_pct < 100.0:
            payout_frac = 0.75
        else:
            payout_frac = 1.0

        credits_bonus = round(q_target * MEASURE_WEIGHTS["credits"] * payout_frac, 2)
        return credits_used_pct, credits_bonus
