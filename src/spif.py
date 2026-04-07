"""SPIF (Sales Performance Incentive Fund) calculator.

Q1 2026 SPIFs:

SDR SPIF
--------
  Flat fee per Closed Won New Business deal where:
    - The deal closes within 8 weeks (56 days) of the SDR's SAO discovery date
    - Close date is in Q1 2026 (Jan–Mar)
  Payout: GBP £400 | SEK 5,000 | EUR 460 (approx)
  Payment month: month the deal closes

AE SPIF
-------
  Winner: FIRST AE to hit their individual Q1 target with close date < 2026-03-01
  Prize:  GBP £1,000 | SEK 12,400
  Payment month: April 2026
  Targets configured in data/spif_targets.csv (fill in q1_target_eur per AE)

Both SPIFs return a DataFrame with columns:
  employee_id, spif_id, description, amount, currency, payment_month
"""

from __future__ import annotations

import os
import re

import pandas as pd


# ---------------------------------------------------------------------------
# Rate tables
# ---------------------------------------------------------------------------

SDR_SPIF_RATES = {
    "GBP": 400,
    "SEK": 5000,
    "EUR": 460,
}

AE_SPIF_RATES = {
    "GBP": 1000,
    "SEK": 12400,
    "EUR": 1150,
}

# Q1 2026 window
Q1_START = pd.Timestamp("2026-01-01")
Q1_END   = pd.Timestamp("2026-03-31")
AE_SPIF_CUTOFF   = pd.Timestamp("2026-03-01")   # AE must hit target BEFORE this date
AE_SPIF_PAYDAY   = pd.Timestamp("2026-04-01")   # April paycheck
SDR_SPIF_WEEKS   = 8                            # 8 weeks = 56 days
_ENCODINGS = ["utf-8", "cp1252", "utf-8-sig", "latin-1"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_csv(path: str) -> pd.DataFrame:
    for enc in _ENCODINGS:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {os.path.basename(path)}")


def _calc_first_year_acv(opp_lines: pd.DataFrame) -> float:
    """1st-year ACV from RR product lines (reuse logic from closed_won_commission)."""
    rr = opp_lines[
        opp_lines["Product Code"].astype(str).str.upper().str.startswith("RR")
    ].copy()
    if rr.empty:
        return 0.0
    contract_start = rr["line_start"].dropna().min()
    if pd.isna(contract_start):
        return 0.0
    cutoff = contract_start + pd.DateOffset(years=1)
    total = 0.0
    for _, line in rr.iterrows():
        ls, le = line["line_start"], line["line_end"]
        if pd.isna(ls) or pd.isna(le) or ls >= cutoff:
            continue
        total_days = (le - ls).days
        if total_days <= 0:
            continue
        included = (min(le, cutoff) - ls).days
        frac = included / total_days
        total += float(line.get("Price (converted)", 0) or 0) * \
                 float(line.get("Duration (years)", 1) or 1) * \
                 float(line.get("Quantity", 1) or 1) * frac
    return round(total, 2)


# ---------------------------------------------------------------------------
# SDR SPIF
# ---------------------------------------------------------------------------

def calculate_sdr_spif(
    sdr_activities: pd.DataFrame,
    closed_won: pd.DataFrame,
    employees: pd.DataFrame,
) -> pd.DataFrame:
    """Return one row per qualifying SDR SPIF deal.

    Matching logic:
      sdr_activities.opportunity_id (= Opportunity Name from SAO data)
      == closed_won.opportunity_name (= Opportunity Name from InputData)

    Only deals closing in Q1 2026 where close_date - sao_date <= 56 days qualify.
    """
    rows = []

    if sdr_activities.empty or closed_won.empty:
        return _empty_spif_df()

    # Need opportunity_name in closed_won (from InputData path)
    if "opportunity_name" not in closed_won.columns:
        return _empty_spif_df()

    # Filter closed_won to Q1 2026
    cw_q1 = closed_won[
        (closed_won["month"] >= Q1_START) &
        (closed_won["month"] <= Q1_END) &
        (~closed_won["is_forecast"])  # only confirmed invoiced deals
    ].copy()

    if cw_q1.empty:
        return _empty_spif_df()

    # Earliest SAO date per (employee_id, opportunity_id)
    sao_dates = (
        sdr_activities.groupby(["employee_id", "opportunity_id"])["date"]
        .min()
        .reset_index()
        .rename(columns={"date": "sao_date", "opportunity_id": "opp_name_sao"})
    )

    # One commission row per unique (employee_id, opportunity_name) pair in Q1
    cw_unique = cw_q1.drop_duplicates(subset=["employee_id", "opportunity_name"])

    # Join: match sao opportunity_id → closed_won opportunity_name
    merged = cw_unique.merge(
        sao_dates,
        left_on=["employee_id", "opportunity_name"],
        right_on=["employee_id", "opp_name_sao"],
        how="inner",
    )

    if merged.empty:
        print("[SPIF] SDR: no SAO→CW matches found for Q1 2026")
        return _empty_spif_df()

    # Check 8-week window
    merged["days_to_close"] = (merged["close_date"] - merged["sao_date"]).dt.days
    qualifying = merged[merged["days_to_close"] <= (SDR_SPIF_WEEKS * 7)].copy()

    if qualifying.empty:
        print("[SPIF] SDR: no deals closed within 8 weeks of SAO in Q1 2026")
        return _empty_spif_df()

    # Build award rows
    emp_lookup = employees.set_index("employee_id")["currency"].to_dict()
    emp_name   = employees.set_index("employee_id")["name"].to_dict()

    for _, r in qualifying.iterrows():
        emp_id   = r["employee_id"]
        currency = emp_lookup.get(emp_id, "GBP")
        amount   = SDR_SPIF_RATES.get(currency, SDR_SPIF_RATES["GBP"])
        opp      = r["opportunity_name"]
        days     = int(r["days_to_close"])

        rows.append({
            "employee_id":   emp_id,
            "name":          emp_name.get(emp_id, emp_id),
            "spif_id":       "sdr_q1_2026_8week",
            "description":   f"SDR Q1 SPIF — {opp} (closed {days}d after SAO)",
            "amount":        amount,
            "currency":      currency,
            "payment_month": r["month"],
            "sao_date":      r["sao_date"].strftime("%Y-%m-%d"),
            "close_date":    r["close_date"].strftime("%Y-%m-%d"),
            "days_to_close": days,
            "opportunity":   opp,
        })

    if rows:
        print(f"[SPIF] SDR: {len(rows)} qualifying deal(s) for Q1 SPIF")

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# AE SPIF
# ---------------------------------------------------------------------------

def calculate_ae_spif(
    data_dir: str,
    employees: pd.DataFrame,
    fx_rates: pd.DataFrame,
) -> pd.DataFrame:
    """Return one row for the winning AE (first to hit Q1 target before March 1).

    Reads:
      data/InputData.csv       — AE closed won deals (Opportunity Owner)
      data/spif_targets.csv    — per-AE Q1 targets (q1_target_eur)
      data/fx_rates.csv        — FX for ACV conversion
    """
    input_path  = os.path.join(data_dir, "InputData.csv")
    target_path = os.path.join(data_dir, "spif_targets.csv")

    if not os.path.exists(target_path):
        print("[SPIF] AE: spif_targets.csv not found — skipped")
        return _empty_spif_df()

    targets = pd.read_csv(target_path)
    targets = targets[targets["spif_id"] == "ae_q1_2026"].copy()
    targets["q1_target_eur"] = pd.to_numeric(targets["q1_target_eur"], errors="coerce").fillna(0)
    targets = targets[targets["q1_target_eur"] > 0]

    if targets.empty:
        print("[SPIF] AE: no targets set in spif_targets.csv — fill in q1_target_eur to activate")
        return _empty_spif_df()

    if not os.path.exists(input_path):
        return _empty_spif_df()

    raw = _read_csv(input_path)

    # Filter: Closed Won + New Business + close before March 1 2026
    raw["close_date"] = pd.to_datetime(
        raw["Close Date"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce"
    )
    ae_cw = raw[
        (raw["Stage"].str.strip().str.lower() == "closed won") &
        (raw["Type"].str.strip().str.lower() == "new business") &
        (raw["close_date"] >= Q1_START) &
        (raw["close_date"] < AE_SPIF_CUTOFF) &
        (raw["Opportunity Owner"].notna()) &
        (raw["Opportunity Owner"].astype(str).str.strip() != "")
    ].copy()

    if ae_cw.empty:
        print("[SPIF] AE: no Q1 Closed Won deals before March 1")
        return _empty_spif_df()

    # Parse line dates + numeric fields for ACV calculation
    ae_cw["line_start"] = pd.to_datetime(
        ae_cw["Start Date"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce"
    )
    ae_cw["line_end"] = pd.to_datetime(
        ae_cw["End Date"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce"
    )
    ae_cw["Price (converted)"] = pd.to_numeric(
        ae_cw["Price (converted)"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0.0)
    ae_cw["Duration (years)"] = pd.to_numeric(ae_cw["Duration (years)"], errors="coerce").fillna(1.0)
    ae_cw["Quantity"]         = pd.to_numeric(ae_cw["Quantity"], errors="coerce").fillna(1.0)

    # Calculate 1st-year ACV per opportunity
    acv_by_opp = {}
    for opp_id, grp in ae_cw.groupby("Opportunity Id Casesafe"):
        acv_by_opp[opp_id] = _calc_first_year_acv(grp)

    # Build opportunity-level table (one row per opp, with close_date and AE)
    opp_level = (
        ae_cw[["Opportunity Id Casesafe", "Opportunity Name", "Opportunity Owner", "close_date"]]
        .drop_duplicates("Opportunity Id Casesafe")
        .copy()
    )
    opp_level["acv_eur"] = opp_level["Opportunity Id Casesafe"].map(acv_by_opp).fillna(0.0)
    opp_level["_owner_lower"] = opp_level["Opportunity Owner"].astype(str).str.strip().str.lower()

    # Match AE names to employees
    ae_emps = employees[employees["role"] == "ae"][["employee_id", "name", "currency"]].copy()
    ae_emps["_name_lower"] = ae_emps["name"].str.strip().str.lower()

    opp_level = opp_level.merge(
        ae_emps[["employee_id", "currency", "_name_lower"]],
        left_on="_owner_lower",
        right_on="_name_lower",
        how="inner",
    )

    if opp_level.empty:
        print("[SPIF] AE: Opportunity Owner names did not match any AE in Humaans")
        return _empty_spif_df()

    # Also filter to AEs with a target set
    target_ids = set(targets["employee_id"].astype(str))
    opp_level = opp_level[opp_level["employee_id"].astype(str).isin(target_ids)]

    if opp_level.empty:
        print("[SPIF] AE: no matched AEs have a target set")
        return _empty_spif_df()

    # Sort chronologically; track cumulative ACV per AE to find first to hit target
    opp_level = opp_level.sort_values("close_date")
    targets_lookup = targets.set_index("employee_id")["q1_target_eur"].to_dict()
    cumulative: dict[str, float] = {}
    winner_id:   str | None = None
    winner_date: pd.Timestamp | None = None

    for _, row in opp_level.iterrows():
        eid = str(row["employee_id"])
        cumulative[eid] = cumulative.get(eid, 0.0) + float(row["acv_eur"])
        target = float(targets_lookup.get(eid, targets_lookup.get(int(eid) if eid.isdigit() else eid, 0)))
        if target > 0 and cumulative[eid] >= target:
            winner_id   = eid
            winner_date = row["close_date"]
            break   # first to hit target wins

    if winner_id is None:
        print("[SPIF] AE: no AE hit their Q1 target before March 1 — no winner yet")
        return _empty_spif_df()

    winner_row = ae_emps[ae_emps["employee_id"].astype(str) == winner_id].iloc[0]
    currency   = winner_row["currency"]
    amount     = AE_SPIF_RATES.get(currency, AE_SPIF_RATES["GBP"])
    won_acv    = round(cumulative[winner_id], 2)

    print(f"[SPIF] AE: winner = {winner_row['name']} "
          f"(hit target on {winner_date.strftime('%Y-%m-%d')}, ACV = €{won_acv:,.0f})")

    return pd.DataFrame([{
        "employee_id":   winner_id,
        "name":          winner_row["name"],
        "spif_id":       "ae_q1_2026_first_to_target",
        "description":   f"AE Q1 SPIF — First to target (hit €{won_acv:,.0f} ACV on {winner_date.strftime('%d %b %Y')})",
        "amount":        amount,
        "currency":      currency,
        "payment_month": AE_SPIF_PAYDAY,
        "sao_date":      None,
        "close_date":    winner_date.strftime("%Y-%m-%d"),
        "days_to_close": None,
        "opportunity":   f"Cumulative Q1 ACV €{won_acv:,.0f}",
    }])


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------

def calculate_all_spifs(
    data_dir: str,
    sdr_activities: pd.DataFrame,
    closed_won: pd.DataFrame,
    employees: pd.DataFrame,
    fx_rates: pd.DataFrame,
) -> pd.DataFrame:
    parts = []

    sdr = calculate_sdr_spif(sdr_activities, closed_won, employees)
    if not sdr.empty:
        parts.append(sdr)

    ae = calculate_ae_spif(data_dir, employees, fx_rates)
    if not ae.empty:
        parts.append(ae)

    if not parts:
        return _empty_spif_df()
    return pd.concat(parts, ignore_index=True)


def _empty_spif_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "employee_id", "name", "spif_id", "description",
        "amount", "currency", "payment_month",
        "sao_date", "close_date", "days_to_close", "opportunity",
    ])
