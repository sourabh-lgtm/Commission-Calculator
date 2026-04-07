import pandas as pd
from src.commission_plans.base import BaseCommissionPlan
from src.helpers import get_fx_rate, quarter_months, quarter_end_month

# ---------------------------------------------------------------------------
# Rate tables  (fixed per-SAO amounts in local currency)
# ---------------------------------------------------------------------------
FIXED_RATES = {
    "SEK": {"outbound_sao": 1300, "inbound_sao": 590, "accelerator_sao": 2000},
    "GBP": {"outbound_sao": 100,  "inbound_sao": 47,  "accelerator_sao": 155},
    "EUR": {"outbound_sao": 115,  "inbound_sao": 55,  "accelerator_sao": 175},
}

# Percentage rates applied to ACV in EUR then FX'd to local currency
PERCENTAGE_RATES = {
    "outbound_closed_won": 0.05,   # 5 % of ACV
    "inbound_closed_won":  0.01,   # 1 % of ACV
}

QUARTERLY_SAO_TARGET = 9   # trigger threshold for accelerator
MONTHLY_SAO_TARGET   = 3   # used for attainment % display only


class SDRCommissionPlan(BaseCommissionPlan):
    role = "sdr"

    def get_rates(self, currency: str) -> dict:
        return FIXED_RATES.get(currency, FIXED_RATES["EUR"])

    def get_components(self) -> list[str]:
        return [
            "outbound_sao_count",
            "inbound_sao_count",
            "outbound_sao_comm",
            "inbound_sao_comm",
            "outbound_cw_acv_eur",
            "inbound_cw_acv_eur",
            "outbound_cw_comm",
            "inbound_cw_comm",
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
    ) -> dict:
        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        rates    = self.get_rates(currency)
        fx_rate  = get_fx_rate(fx_df, month, currency)

        # Filter to this employee & month
        act = activities[
            (activities["employee_id"] == emp_id) & (activities["month"] == month)
        ]
        cw = closed_won[
            (closed_won["employee_id"] == emp_id) & (closed_won["month"] == month)
        ]

        # SAO counts
        out_saos = int((act["sao_type"] == "outbound").sum())
        in_saos  = int((act["sao_type"] == "inbound").sum())

        # Fixed-rate SAO commissions
        out_sao_comm = out_saos * rates["outbound_sao"]
        in_sao_comm  = in_saos  * rates["inbound_sao"]

        # Closed-won ACV commissions (EUR base × % × FX)
        out_cw = cw[cw["sao_type"] == "outbound"]
        in_cw  = cw[cw["sao_type"] == "inbound"]

        out_cw_acv_eur = float(out_cw["acv_eur"].sum())
        in_cw_acv_eur  = float(in_cw["acv_eur"].sum())

        out_cw_comm = out_cw_acv_eur * PERCENTAGE_RATES["outbound_closed_won"] * fx_rate
        in_cw_comm  = in_cw_acv_eur  * PERCENTAGE_RATES["inbound_closed_won"]  * fx_rate

        total = out_sao_comm + in_sao_comm + out_cw_comm + in_cw_comm

        return {
            "employee_id":         emp_id,
            "month":               month,
            "currency":            currency,
            "fx_rate":             fx_rate,
            "outbound_sao_count":  out_saos,
            "inbound_sao_count":   in_saos,
            "total_sao_count":     out_saos + in_saos,
            "outbound_sao_comm":   round(out_sao_comm, 2),
            "inbound_sao_comm":    round(in_sao_comm, 2),
            "outbound_cw_acv_eur": round(out_cw_acv_eur, 2),
            "inbound_cw_acv_eur":  round(in_cw_acv_eur, 2),
            "outbound_cw_comm":    round(out_cw_comm, 2),
            "inbound_cw_comm":     round(in_cw_comm, 2),
            "accelerator_topup":   0.0,   # filled in by quarterly pass
            "total_commission":    round(total, 2),
            "monthly_sao_target":  MONTHLY_SAO_TARGET,
            "attainment_pct":      round((out_saos / MONTHLY_SAO_TARGET) * 100, 1),
        }

    # ------------------------------------------------------------------
    # Quarterly accelerator
    # ------------------------------------------------------------------
    def calculate_quarterly_accelerator(
        self,
        employee: pd.Series,
        year: int,
        quarter: int,
        activities: pd.DataFrame,
    ) -> dict:
        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        rates    = self.get_rates(currency)

        months = quarter_months(year, quarter)
        q_end  = quarter_end_month(months[0])

        act = activities[
            (activities["employee_id"] == emp_id) &
            (activities["month"].isin(months))
        ].sort_values("date")

        total_saos    = len(act)
        out_saos      = int((act["sao_type"] == "outbound").sum())
        in_saos       = int((act["sao_type"] == "inbound").sum())
        excess        = max(0, total_saos - QUARTERLY_SAO_TARGET)

        # Only outbound SAOs in the "excess" positions earn the accelerator top-up.
        # We walk the chronological list and count how many excess positions are outbound.
        excess_outbound = 0
        if excess > 0:
            types = list(act["sao_type"])
            count = 0
            for t in types:
                count += 1
                if count > QUARTERLY_SAO_TARGET and t == "outbound":
                    excess_outbound += 1

        topup_per_sao = rates["accelerator_sao"] - rates["outbound_sao"]
        accelerator_topup = round(excess_outbound * topup_per_sao, 2)

        return {
            "employee_id":        emp_id,
            "year":               year,
            "quarter":            quarter,
            "quarter_end_month":  q_end,
            "currency":           currency,
            "total_saos":         total_saos,
            "outbound_saos":      out_saos,
            "inbound_saos":       in_saos,
            "threshold":          QUARTERLY_SAO_TARGET,
            "excess_saos":        excess,
            "excess_outbound":    excess_outbound,
            "topup_per_sao":      topup_per_sao,
            "accelerator_topup":  accelerator_topup,
        }

    # ------------------------------------------------------------------
    # Detailed workings rows (one row per SAO / per deal)
    # ------------------------------------------------------------------
    def get_workings_rows(
        self,
        employee: pd.Series,
        month: pd.Timestamp,
        activities: pd.DataFrame,
        closed_won: pd.DataFrame,
        fx_df: pd.DataFrame,
    ) -> list[dict]:
        emp_id   = employee["employee_id"]
        currency = employee["currency"]
        rates    = self.get_rates(currency)
        fx_rate  = get_fx_rate(fx_df, month, currency)

        rows = []

        # SAO rows
        act = activities[
            (activities["employee_id"] == emp_id) & (activities["month"] == month)
        ].sort_values("date")

        for _, r in act.iterrows():
            sao_type = r["sao_type"]
            rate = rates["outbound_sao"] if sao_type == "outbound" else rates["inbound_sao"]
            rows.append({
                "type":           "SAO",
                "date":           r["date"].strftime("%Y-%m-%d"),
                "opportunity_id": r["opportunity_id"],
                "sao_type":       sao_type,
                "acv_eur":        None,
                "fx_rate":        None,
                "rate_desc":      f"{currency} {rate:,} / SAO",
                "commission":     rate,
                "currency":       currency,
            })

        # Closed won rows
        cw = closed_won[
            (closed_won["employee_id"] == emp_id) & (closed_won["month"] == month)
        ].sort_values("invoice_date")

        for _, r in cw.iterrows():
            sao_type = r["sao_type"]
            pct = PERCENTAGE_RATES["outbound_closed_won"] if sao_type == "outbound" else PERCENTAGE_RATES["inbound_closed_won"]
            acv_eur = float(r["acv_eur"])
            comm = round(acv_eur * pct * fx_rate, 2)
            rows.append({
                "type":           "Closed Won",
                "date":           r["invoice_date"].strftime("%Y-%m-%d"),
                "opportunity_id": r["opportunity_id"],
                "sao_type":       sao_type,
                "acv_eur":        acv_eur,
                "fx_rate":        fx_rate,
                "rate_desc":      f"{pct*100:.0f}% of ACV × {fx_rate:.4f}",
                "commission":     comm,
                "currency":       currency,
            })

        return rows
