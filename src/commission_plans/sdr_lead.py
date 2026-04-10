"""SDR Team Lead commission plan — FY26.

Bonus structure (quarterly, paid at quarter-end):
  Annual bonus pot: £8,800 → split as £2,200/quarter.

  Two team-level measures:
    1. Team SAO count  — 35% weight → £770/quarter
    2. Team closed-won 1st-year ACV (EUR) — 65% weight → £1,430/quarter

  Each measure uses a tiered payout:
    < 50% of target  → 0%   of measure pot
    50–75% of target → 50%  of measure pot
    75–100% of target → 75% of measure pot
    ≥ 100% of target  → 100% of measure pot

Targets are loaded from data/sdr_lead_targets.csv:
  sao_team_target_q    — team SAOs per quarter (default: 54)
  acv_team_target_eur_q — team ACV per quarter in EUR (default: €223,500)
  quarterly_bonus_gbp  — total quarterly bonus pot (default: £2,200)

Team SAO count: aggregated from model.sdr_activities (all SDR employees).
Team ACV: aggregated from model.closed_won (SDR closed-won data, passed via
  cs_performance['sdr_closed_won']).

The SDR Lead earns nothing from individual deals; this is a team-level bonus only.
Commission is booked in the quarter-end month.
"""

from __future__ import annotations

import pandas as pd
from src.commission_plans.base import BaseCommissionPlan
from src.helpers import get_fx_rate, quarter_months, quarter_end_month

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MEASURE_WEIGHTS = {
    "sao": 0.35,    # 35% → SAO count
    "acv": 0.65,    # 65% → closed-won ACV
}

# Tiers: (min_attainment_inclusive, payout_fraction)
PAYOUT_TIERS: list[tuple[float, float]] = [
    (1.00, 1.00),
    (0.75, 0.75),
    (0.50, 0.50),
    (0.00, 0.00),
]


def _tiered_payout(attainment: float) -> float:
    """Return payout fraction for a given attainment level."""
    for threshold, payout in PAYOUT_TIERS:
        if attainment >= threshold:
            return payout
    return 0.0


def _get_managed_sdr_ids(
    emp_id: str,
    employees_df: pd.DataFrame,
    quarter_start: pd.Timestamp,
    quarter_end: pd.Timestamp,
) -> set[str]:
    """Return SDR employee_ids that count toward this lead's quarterly commission.

    Includes:
    - Direct current reports (manager_id == emp_id, role sdr/sdr_lead)
    - SDRs currently under OTHER sdr_leads who were hired mid-quarter: those
      SDRs were under this lead before the new hire joined, so they count for
      the full quarter's team performance.
    """
    if employees_df.empty or "manager_id" not in employees_df.columns:
        return set()

    # Direct current reports
    mask = (
        employees_df["manager_id"].astype(str) == str(emp_id)
    ) & employees_df["role"].isin(["sdr", "sdr_lead"])
    managed_ids: set[str] = set(employees_df.loc[mask, "employee_id"].astype(str))

    # Other SDR leads hired during this quarter → their SDRs previously rolled
    # up under this lead, so include them for the full quarter.
    if "employment_start" in employees_df.columns:
        mid_q_leads = employees_df[
            employees_df["role"].isin(["sdr_lead"])
            & (employees_df["employee_id"].astype(str) != str(emp_id))
            & employees_df["employment_start"].notna()
            & (employees_df["employment_start"] >= quarter_start)
            & (employees_df["employment_start"] <= quarter_end)
        ]
        for _, other_lead in mid_q_leads.iterrows():
            other_reports = set(employees_df[
                (employees_df["manager_id"].astype(str) == str(other_lead["employee_id"]))
                & employees_df["role"].isin(["sdr", "sdr_lead"])
            ]["employee_id"].astype(str))
            managed_ids |= other_reports

    # Include the lead themselves — sdr_leads also log SAOs directly
    managed_ids.add(str(emp_id))

    return managed_ids


class SDRLeadCommissionPlan(BaseCommissionPlan):
    role = "sdr_lead"

    def get_rates(self, currency: str) -> dict:
        return {"quarterly_bonus_gbp": 2200.0}

    def get_components(self) -> list[str]:
        return [
            "sao_team_count",
            "sao_team_target",
            "sao_attainment_pct",
            "sao_payout_pct",
            "sao_bonus",
            "acv_team_eur",
            "acv_team_target_eur",
            "acv_attainment_pct",
            "acv_payout_pct",
            "acv_bonus",
            "accelerator_topup",
            "total_commission",
        ]

    # ------------------------------------------------------------------
    # Monthly pass — always zero (bonus is quarterly team-level)
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

        return {
            "employee_id":          emp_id,
            "month":                month,
            "currency":             currency,
            "fx_rate":              fx_rate,
            "sao_team_count":       0,
            "sao_team_target":      0,
            "sao_attainment_pct":   0.0,
            "sao_payout_pct":       0.0,
            "sao_bonus":            0.0,
            "acv_team_eur":         0.0,
            "acv_team_target_eur":  0.0,
            "acv_attainment_pct":   0.0,
            "acv_payout_pct":       0.0,
            "acv_bonus":            0.0,
            "accelerator_topup":    0.0,
            "total_commission":     0.0,
        }

    # ------------------------------------------------------------------
    # Quarterly pass — team SAO + ACV vs targets
    # ------------------------------------------------------------------
    def calculate_quarterly_accelerator(
        self,
        employee: pd.Series,
        year: int,
        quarter: int,
        activities: pd.DataFrame,       # ALL SDR activities (all employees)
        salary_history: pd.DataFrame = None,
        cs_performance: dict = None,
    ) -> dict:
        emp_id   = employee["employee_id"]
        currency = employee["currency"]

        months = quarter_months(year, quarter)
        q_end  = quarter_end_month(months[0])

        # FX rate for GBP payout (SDR Lead is always GBP-paid per contract)
        fx_df   = cs_performance.get("fx_rates", pd.DataFrame()) if cs_performance else pd.DataFrame()

        # --- Load targets for this employee + year ---
        targets_df = cs_performance.get("sdr_lead_targets", pd.DataFrame()) if cs_performance else pd.DataFrame()
        quarterly_bonus_gbp   = 2200.0
        sao_target_q          = 54
        acv_target_eur_q      = 223500.0

        if not targets_df.empty:
            mask = (
                (targets_df["employee_id"].astype(str) == str(emp_id)) &
                (targets_df["year"].astype(int) == int(year))
            )
            row = targets_df[mask]
            if not row.empty:
                quarterly_bonus_gbp  = float(row["quarterly_bonus_gbp"].iloc[0])
                sao_target_q         = int(row["sao_team_target_q"].iloc[0])
                acv_target_eur_q     = float(row["acv_team_target_eur_q"].iloc[0])

        # --- Resolve managed SDR employee IDs (current reports + mid-quarter hires' reports) ---
        employees_df = cs_performance.get("employees", pd.DataFrame()) if cs_performance else pd.DataFrame()
        managed_ids = _get_managed_sdr_ids(str(emp_id), employees_df, months[0], q_end)

        # --- Measure 1: Team SAO count (only managed SDRs) ---
        q_sao_count = 0
        if not activities.empty and "month" in activities.columns:
            team_saos = activities[activities["month"].isin(months)]
            if managed_ids and "employee_id" in team_saos.columns:
                team_saos = team_saos[team_saos["employee_id"].astype(str).isin(managed_ids)]
            q_sao_count = len(team_saos)

        sao_attainment = q_sao_count / sao_target_q if sao_target_q > 0 else 0.0
        sao_payout_pct = _tiered_payout(sao_attainment)
        sao_pot        = quarterly_bonus_gbp * MEASURE_WEIGHTS["sao"]
        sao_bonus      = round(sao_pot * sao_payout_pct, 2)

        # --- Measure 2: Team closed-won ACV (EUR, only managed SDRs) ---
        q_acv_eur = 0.0
        sdr_cw = cs_performance.get("sdr_closed_won", pd.DataFrame()) if cs_performance else pd.DataFrame()
        if not sdr_cw.empty and "month" in sdr_cw.columns:
            team_cw = sdr_cw[sdr_cw["month"].isin(months)]
            if managed_ids and "employee_id" in team_cw.columns:
                team_cw = team_cw[team_cw["employee_id"].astype(str).isin(managed_ids)]
            # Only count actual invoices (not forecast) to avoid double-counting
            if "is_forecast" in team_cw.columns:
                team_cw = team_cw[~team_cw["is_forecast"]]
            q_acv_eur = float(team_cw["acv_eur"].sum())

        acv_attainment = q_acv_eur / acv_target_eur_q if acv_target_eur_q > 0 else 0.0
        acv_payout_pct = _tiered_payout(acv_attainment)
        acv_pot        = quarterly_bonus_gbp * MEASURE_WEIGHTS["acv"]
        acv_bonus      = round(acv_pot * acv_payout_pct, 2)

        total_bonus = round(sao_bonus + acv_bonus, 2)

        # Convert to employee's local currency if not GBP
        # (SDR Lead contract is denominated in GBP, so FX only if employee paid in other currency)
        if currency != "GBP" and not fx_df.empty:
            fx_to_gbp = get_fx_rate(fx_df, q_end, "GBP")   # EUR → GBP
            fx_to_local = get_fx_rate(fx_df, q_end, currency)
            if fx_to_gbp > 0:
                total_bonus_eur = total_bonus / fx_to_gbp   # GBP → EUR
                total_bonus = round(total_bonus_eur * fx_to_local, 2)
                sao_bonus   = round(sao_bonus / fx_to_gbp * fx_to_local, 2)
                acv_bonus   = round(acv_bonus / fx_to_gbp * fx_to_local, 2)

        return {
            "employee_id":          emp_id,
            "year":                 year,
            "quarter":              quarter,
            "quarter_end_month":    q_end,
            "currency":             currency,
            # SAO measure
            "sao_team_count":       q_sao_count,
            "sao_team_target":      sao_target_q,
            "sao_attainment_pct":   round(sao_attainment * 100, 1),
            "sao_payout_pct":       sao_payout_pct * 100,
            "sao_bonus":            sao_bonus,
            # ACV measure
            "acv_team_eur":         round(q_acv_eur, 2),
            "acv_team_target_eur":  acv_target_eur_q,
            "acv_attainment_pct":   round(acv_attainment * 100, 1),
            "acv_payout_pct":       acv_payout_pct * 100,
            "acv_bonus":            acv_bonus,
            # Total
            "accelerator_topup":    total_bonus,
        }

    # ------------------------------------------------------------------
    # Workings rows — team activity detail for the dashboard
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
        """Return one row per team measure (SAO + ACV) for quarter-end months.

        Non-quarter-end months have no commission, so return an empty list.
        """
        # Only emit rows at quarter-end months (Mar / Jun / Sep / Dec)
        if month.month not in (3, 6, 9, 12):
            return []

        currency = employee["currency"]
        q        = (month.month - 1) // 3 + 1
        year     = month.year
        months   = quarter_months(year, q)
        q_end    = quarter_end_month(months[0])
        fx_rate  = get_fx_rate(fx_df, q_end, currency)

        # Load targets
        targets_df = cs_performance.get("sdr_lead_targets", pd.DataFrame()) if cs_performance else pd.DataFrame()
        quarterly_bonus_gbp = 2200.0
        sao_target_q        = 54
        acv_target_eur_q    = 223500.0
        emp_id = employee["employee_id"]

        if not targets_df.empty:
            mask = (
                (targets_df["employee_id"].astype(str) == str(emp_id)) &
                (targets_df["year"].astype(int) == int(year))
            )
            row = targets_df[mask]
            if not row.empty:
                quarterly_bonus_gbp = float(row["quarterly_bonus_gbp"].iloc[0])
                sao_target_q        = int(row["sao_team_target_q"].iloc[0])
                acv_target_eur_q    = float(row["acv_team_target_eur_q"].iloc[0])

        # Resolve managed SDR employee IDs (current reports + mid-quarter hires' reports)
        employees_df = cs_performance.get("employees", pd.DataFrame()) if cs_performance else pd.DataFrame()
        managed_ids = _get_managed_sdr_ids(str(emp_id), employees_df, months[0], q_end)

        # Team SAO count (only managed SDRs)
        q_sao_count = 0
        if not activities.empty and "month" in activities.columns:
            team_saos = activities[activities["month"].isin(months)]
            if managed_ids and "employee_id" in team_saos.columns:
                team_saos = team_saos[team_saos["employee_id"].astype(str).isin(managed_ids)]
            q_sao_count = len(team_saos)

        sao_attainment = q_sao_count / sao_target_q if sao_target_q > 0 else 0.0
        sao_payout_pct = _tiered_payout(sao_attainment)
        sao_bonus      = round(quarterly_bonus_gbp * MEASURE_WEIGHTS["sao"] * sao_payout_pct, 2)

        # Team ACV (only managed SDRs)
        q_acv_eur = 0.0
        sdr_cw = cs_performance.get("sdr_closed_won", pd.DataFrame()) if cs_performance else pd.DataFrame()
        if not sdr_cw.empty and "month" in sdr_cw.columns:
            team_cw = sdr_cw[sdr_cw["month"].isin(months)]
            if managed_ids and "employee_id" in team_cw.columns:
                team_cw = team_cw[team_cw["employee_id"].astype(str).isin(managed_ids)]
            if "is_forecast" in team_cw.columns:
                team_cw = team_cw[~team_cw["is_forecast"]]
            q_acv_eur = float(team_cw["acv_eur"].sum())

        acv_attainment = q_acv_eur / acv_target_eur_q if acv_target_eur_q > 0 else 0.0
        acv_payout_pct = _tiered_payout(acv_attainment)
        acv_bonus      = round(quarterly_bonus_gbp * MEASURE_WEIGHTS["acv"] * acv_payout_pct, 2)

        date_str = q_end.strftime("%Y-%m-%d")
        return [
            {
                "type":             "Team SAO",
                "date":             date_str,
                "opportunity_name": f"Team SAOs: {q_sao_count} / {sao_target_q}  ({sao_attainment * 100:.0f}% attainment)",
                "sao_type":         "",
                "acv_eur":          None,
                "fx_rate":          fx_rate,
                "rate_desc":        f"35% weight — {sao_payout_pct * 100:.0f}% tier payout",
                "commission":       sao_bonus,
            },
            {
                "type":             "Team ACV",
                "date":             date_str,
                "opportunity_name": f"Team ACV: \u20ac{q_acv_eur:,.0f} / \u20ac{acv_target_eur_q:,.0f}  ({acv_attainment * 100:.0f}% attainment)",
                "sao_type":         "",
                "acv_eur":          round(q_acv_eur, 2),
                "fx_rate":          fx_rate,
                "rate_desc":        f"65% weight — {acv_payout_pct * 100:.0f}% tier payout",
                "commission":       acv_bonus,
            },
        ]
