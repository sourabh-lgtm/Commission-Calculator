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
        salary_history: pd.DataFrame = None,   # unused for SDRs
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
        # Split actual (invoiced) vs forecast rows
        has_forecast = "is_forecast" in cw.columns
        cw_actual   = cw[~cw["is_forecast"]] if has_forecast else cw
        cw_forecast = cw[cw["is_forecast"]]  if has_forecast else pd.DataFrame()

        out_cw_actual   = cw_actual[cw_actual["sao_type"] == "outbound"]
        in_cw_actual    = cw_actual[cw_actual["sao_type"] == "inbound"]
        out_cw_forecast = cw_forecast[cw_forecast["sao_type"] == "outbound"] if not cw_forecast.empty else pd.DataFrame()
        in_cw_forecast  = cw_forecast[cw_forecast["sao_type"] == "inbound"]  if not cw_forecast.empty else pd.DataFrame()

        out_cw_acv_eur          = float(out_cw_actual["acv_eur"].sum())
        in_cw_acv_eur           = float(in_cw_actual["acv_eur"].sum())
        out_cw_forecast_acv_eur = float(out_cw_forecast["acv_eur"].sum()) if not out_cw_forecast.empty else 0.0
        in_cw_forecast_acv_eur  = float(in_cw_forecast["acv_eur"].sum())  if not in_cw_forecast.empty  else 0.0

        out_cw_comm          = out_cw_acv_eur          * PERCENTAGE_RATES["outbound_closed_won"] * fx_rate
        in_cw_comm           = in_cw_acv_eur           * PERCENTAGE_RATES["inbound_closed_won"]  * fx_rate
        out_cw_forecast_comm = out_cw_forecast_acv_eur * PERCENTAGE_RATES["outbound_closed_won"] * fx_rate
        in_cw_forecast_comm  = in_cw_forecast_acv_eur  * PERCENTAGE_RATES["inbound_closed_won"]  * fx_rate

        # Only actual (invoiced) amounts count toward confirmed commission
        total = out_sao_comm + in_sao_comm + out_cw_comm + in_cw_comm

        return {
            "employee_id":                emp_id,
            "month":                      month,
            "currency":                   currency,
            "fx_rate":                    fx_rate,
            "outbound_sao_count":         out_saos,
            "inbound_sao_count":          in_saos,
            "total_sao_count":            out_saos + in_saos,
            "outbound_sao_comm":          round(out_sao_comm, 2),
            "inbound_sao_comm":           round(in_sao_comm, 2),
            # Actual (invoiced) closed won
            "outbound_cw_acv_eur":        round(out_cw_acv_eur, 2),
            "inbound_cw_acv_eur":         round(in_cw_acv_eur, 2),
            "outbound_cw_comm":           round(out_cw_comm, 2),
            "inbound_cw_comm":            round(in_cw_comm, 2),
            # Forecast (unmatched to NetSuite invoice yet)
            "outbound_cw_forecast_acv":   round(out_cw_forecast_acv_eur, 2),
            "inbound_cw_forecast_acv":    round(in_cw_forecast_acv_eur, 2),
            "outbound_cw_forecast_comm":  round(out_cw_forecast_comm, 2),
            "inbound_cw_forecast_comm":   round(in_cw_forecast_comm, 2),
            "accelerator_topup":          0.0,   # filled in by quarterly pass
            "total_commission":           round(total, 2),
            "monthly_sao_target":         MONTHLY_SAO_TARGET,
            "attainment_pct":             round((out_saos / MONTHLY_SAO_TARGET) * 100, 1),
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
        salary_history: pd.DataFrame = None,   # unused for SDRs
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

        total_saos = len(act)
        out_saos   = int((act["sao_type"] == "outbound").sum())
        in_saos    = int((act["sao_type"] == "inbound").sum())

        # Accelerator triggers only when outbound SAOs >= threshold.
        # Excess = all SAOs (inbound + outbound) beyond the threshold.
        excess_outbound = max(0, total_saos - QUARTERLY_SAO_TARGET) if out_saos >= QUARTERLY_SAO_TARGET else 0

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
            "excess_saos":        excess_outbound,
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

        # Closed won rows (actual invoices + forecast)
        cw = closed_won[
            (closed_won["employee_id"] == emp_id) & (closed_won["month"] == month)
        ].sort_values("invoice_date")

        for _, r in cw.iterrows():
            sao_type   = r["sao_type"]
            is_forecast = bool(r.get("is_forecast", False))
            pct = PERCENTAGE_RATES["outbound_closed_won"] if sao_type == "outbound" else PERCENTAGE_RATES["inbound_closed_won"]
            acv_eur = float(r["acv_eur"])
            comm = round(acv_eur * pct * fx_rate, 2)

            inv_date = r.get("invoice_date")
            date_str = inv_date.strftime("%Y-%m-%d") if pd.notna(inv_date) else ""
            doc_num  = str(r.get("document_number", "")).strip()
            opp_name = str(r.get("opportunity_name", r.get("opportunity_id", ""))).strip()

            row_type = "Forecast CW" if is_forecast else "Closed Won"
            label    = f"{pct*100:.0f}% of ACV × {fx_rate:.4f}"
            if is_forecast:
                label += " (forecast)"

            rows.append({
                "type":             row_type,
                "date":             date_str,
                "opportunity_id":   r["opportunity_id"],
                "opportunity_name": opp_name,
                "document_number":  doc_num,
                "sao_type":         sao_type,
                "acv_eur":          acv_eur,
                "fx_rate":          fx_rate,
                "rate_desc":        label,
                "commission":       comm,
                "currency":         currency,
                "is_forecast":      is_forecast,
            })

        return rows
