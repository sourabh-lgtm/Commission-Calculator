"""Closed won commission builder.

Combines:
  - InputData.csv   (Salesforce all-opp export, line-item level) — source of ACV, SDR, Lead Source
  - InvoiceSearchCommissions.csv (NetSuite) — source of actual invoice timing & amount

ACV calculation (1st year only, RR product codes):
  - Filter lines where Product Code starts with "RR" (recurring)
  - Contract start = earliest line Start Date across all RR lines for the opp
  - Year-1 cutoff = contract start + 1 year
  - Lines starting on or after year-1 cutoff are excluded (year 2+ lines)
  - For lines that start in year 1 but end after year-1 cutoff, prorate:
      fraction = (min(End Date, cutoff) - Start Date).days / (End Date - Start Date).days
  - Line ACV = Price (converted) × Duration (years) × Quantity × fraction
  - Opportunity ACV = sum of all qualifying line ACVs (already in EUR)

Commission logic:
  1. Calculate 1st year ACV per opportunity from product lines.
  2. Match SDR name → employee_id (case-insensitive).
  3. Classify Lead Source → outbound / inbound.
  4. Join to InvoiceSearchCommissions on External ID = Opportunity Id Casesafe.
  5. For MATCHED deals: one commission row per invoice/credit-memo.
       - acv_eur = opportunity 1st year ACV (not the invoice amount)
       - Month  = invoice Period (e.g. "Jan 2026" → 2026-01-01)
       - Credit Memos produce negative acv_eur (clawback proportional to deal ACV)
  6. For UNMATCHED deals: one forecast row per deal.
       - acv_eur = calculated 1st year ACV
       - Month  = Close Date month
       - Flagged is_forecast = True

Note: commission % (5% outbound / 1% inbound) is applied in sdr.py, not here.

Output columns:
  employee_id, opportunity_id, opportunity_name, sao_type, acv_eur,
  invoice_date, month, close_date, is_forecast, document_number, invoice_currency
"""

from __future__ import annotations

import os
import re

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
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


def _parse_subtotal(val) -> float:
    """Parse comma-formatted number string → float.  e.g. '12,500.00' → 12500.0."""
    if pd.isna(val):
        return 0.0
    return float(re.sub(r"[,\s]", "", str(val)))


def _parse_period(val: str) -> pd.Timestamp | None:
    """Parse 'Jan 2026' → 2026-01-01 Timestamp."""
    try:
        return pd.to_datetime(str(val).strip(), format="%b %Y")
    except Exception:
        return None


def _cadence_n_invoices(cadence_str) -> int:
    """Number of invoices per year implied by the Invoicing Cadence field."""
    c = str(cadence_str).strip().lower()
    if "month" in c:
        return 12
    if "quarter" in c:
        return 4
    if "semi" in c or "bi-annual" in c or "biannual" in c or "half" in c:
        return 2
    # "yearly in advance", "annual", "upfront", "one-time", blank, etc.
    return 1


def _classify_lead_source(val) -> str | None:
    v = str(val).strip().lower()
    if v.startswith("outbound"):
        return "outbound"
    if v.startswith("inbound"):
        return "inbound"
    return None


def _get_fx_to_eur(fx_df: pd.DataFrame, month: pd.Timestamp, currency: str) -> float:
    """Return EUR_<currency> rate; caller divides local amount by this to get EUR."""
    if currency == "EUR":
        return 1.0
    col = f"EUR_{currency.upper()}"
    if col not in fx_df.columns:
        return 1.0
    row = fx_df[fx_df["month"] == month]
    if row.empty:
        past = fx_df[fx_df["month"] <= month]
        row = past.iloc[[-1]] if not past.empty else None
        if row is None:
            return 1.0
    return float(row[col].iloc[0])


# ---------------------------------------------------------------------------
# 1st-year ACV calculator
# ---------------------------------------------------------------------------

def _calc_first_year_acv(opp_lines: pd.DataFrame) -> float:
    """Return 1st-year ACV (EUR) for a single opportunity's line items.

    opp_lines must have columns: Product Code, line_start, line_end,
    Price (converted), Duration (years), Quantity.
    Price (converted) is the annual price per unit in EUR.
    TCV of a line = Price × Duration × Quantity.
    """
    # Only recurring product codes
    rr = opp_lines[
        opp_lines["Product Code"].astype(str).str.upper().str.startswith("RR")
    ].copy()

    if rr.empty:
        return 0.0

    # Contract start = earliest line start
    contract_start = rr["line_start"].dropna().min()
    if pd.isna(contract_start):
        return 0.0

    year_1_cutoff = contract_start + pd.DateOffset(years=1)

    total = 0.0
    for _, line in rr.iterrows():
        line_start = line["line_start"]
        line_end   = line["line_end"]

        if pd.isna(line_start) or pd.isna(line_end):
            continue

        # Skip lines that start in year 2+
        if line_start >= year_1_cutoff:
            continue

        total_days = (line_end - line_start).days
        if total_days <= 0:
            continue

        # Prorate if line extends past year-1 cutoff
        included_end  = min(line_end, year_1_cutoff)
        included_days = (included_end - line_start).days
        fraction = included_days / total_days

        price    = float(line.get("Price (converted)", 0) or 0)
        duration = float(line.get("Duration (years)", 1) or 1)
        quantity = float(line.get("Quantity", 1) or 1)

        total += price * duration * quantity * fraction

    return round(total, 2)


def _calc_total_rr_acv(opp_lines: pd.DataFrame) -> float:
    """Return total ACV (EUR) for ALL years of RR lines (no year-1 cutoff).

    Used together with _calc_first_year_acv to derive multi-year incremental ACV:
      multi_year_acv = total_rr_acv - first_year_acv
    """
    rr = opp_lines[
        opp_lines["Product Code"].astype(str).str.upper().str.startswith("RR")
    ].copy()

    if rr.empty:
        return 0.0

    total = 0.0
    for _, line in rr.iterrows():
        line_start = line["line_start"]
        line_end   = line["line_end"]
        if pd.isna(line_start) or pd.isna(line_end):
            continue
        total_days = (line_end - line_start).days
        if total_days <= 0:
            continue
        price    = float(line.get("Price (converted)", 0) or 0)
        duration = float(line.get("Duration (years)", 1) or 1)
        quantity = float(line.get("Quantity", 1) or 1)
        total += price * duration * quantity

    return round(total, 2)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_closed_won_commission(
    data_dir: str,
    employees: pd.DataFrame,
    fx_rates: pd.DataFrame,
) -> pd.DataFrame:
    """Return a normalised closed_won DataFrame for use by commission plans."""
    input_path   = os.path.join(data_dir, "InputData.csv")
    invoice_path = os.path.join(data_dir, "InvoiceSearchCommissions.csv")

    if not os.path.exists(input_path):
        print("[CW] InputData.csv not found — closed won commission skipped")
        return _empty_df()

    # ------------------------------------------------------------------
    # 1. Load InputData.csv (all rows — multiple lines per opportunity)
    # ------------------------------------------------------------------
    raw = _read_csv(input_path)

    required = ["Opportunity Id Casesafe", "Stage", "SDR", "Lead Source", "Close Date",
                "Product Code", "Start Date", "End Date",
                "Price (converted)", "Duration (years)", "Quantity"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        print(f"[CW] InputData.csv missing columns: {missing} — skipped")
        return _empty_df()

    # Filter to Closed Won + New Business + SDR not blank (line level)
    raw = raw[
        (raw["Stage"].str.strip().str.lower() == "closed won") &
        (raw["Type"].str.strip().str.lower() == "new business") &
        (raw["SDR"].notna()) &
        (raw["SDR"].astype(str).str.strip() != "")
    ].copy()

    if raw.empty:
        print("[CW] No Closed Won New Business rows with SDR found in InputData.csv")
        return _empty_df()

    # Parse line-level dates
    raw["line_start"] = pd.to_datetime(raw["Start Date"].astype(str).str.strip(),
                                        format="%d/%m/%Y", errors="coerce")
    raw["line_end"]   = pd.to_datetime(raw["End Date"].astype(str).str.strip(),
                                        format="%d/%m/%Y", errors="coerce")

    # Numeric line columns
    raw["Price (converted)"] = pd.to_numeric(
        raw["Price (converted)"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0.0)
    raw["Duration (years)"] = pd.to_numeric(raw["Duration (years)"], errors="coerce").fillna(1.0)
    raw["Quantity"]         = pd.to_numeric(raw["Quantity"], errors="coerce").fillna(1.0)

    # ------------------------------------------------------------------
    # 2. Calculate 1st-year ACV per opportunity
    # ------------------------------------------------------------------
    acv_by_opp: dict[str, float] = {}
    for opp_id, grp in raw.groupby("Opportunity Id Casesafe"):
        acv_by_opp[str(opp_id).strip()] = _calc_first_year_acv(grp)

    # ------------------------------------------------------------------
    # 3. Build opportunity-level summary (one row per opp)
    # ------------------------------------------------------------------
    opp_cols = ["Opportunity Id Casesafe", "Opportunity Name", "SDR",
                "Lead Source", "Close Date"]
    opps = (
        raw[opp_cols]
        .drop_duplicates(subset=["Opportunity Id Casesafe"])
        .copy()
    )

    opps["close_date"] = pd.to_datetime(
        opps["Close Date"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce"
    )
    opps = opps.dropna(subset=["close_date"])

    opps["sao_type"] = opps["Lead Source"].apply(_classify_lead_source)
    opps = opps[opps["sao_type"].notna()].copy()

    opps["opportunity_id"]   = opps["Opportunity Id Casesafe"].astype(str).str.strip()
    opps["opportunity_name"] = (
        opps["Opportunity Name"].astype(str).str.strip()
        if "Opportunity Name" in opps.columns
        else opps["opportunity_id"]
    )
    opps["acv_eur"] = opps["opportunity_id"].map(acv_by_opp).fillna(0.0)

    # ------------------------------------------------------------------
    # 4. Match SDR name → employee_id
    # ------------------------------------------------------------------
    sdr_emps = employees[employees["role"] == "sdr"][["employee_id", "name"]].copy()
    sdr_emps["name_lower"] = sdr_emps["name"].str.strip().str.lower()
    opps["_sdr_lower"] = opps["SDR"].astype(str).str.strip().str.lower()

    opps = opps.merge(
        sdr_emps[["employee_id", "name_lower"]],
        left_on="_sdr_lower",
        right_on="name_lower",
        how="inner",
    ).drop(columns=["_sdr_lower", "name_lower"])

    if opps.empty:
        print("[CW] No SDR names in InputData matched employees — skipped")
        return _empty_df()

    n_opps = opps["opportunity_id"].nunique()
    n_with_acv = (opps["acv_eur"] > 0).sum()
    print(f"[CW] {n_opps} Closed Won deals matched to SDRs "
          f"({n_with_acv} with 1st-year ACV > 0 from RR lines)")

    # ------------------------------------------------------------------
    # 5. Load InvoiceSearchCommissions.csv
    # ------------------------------------------------------------------
    rows = []

    if os.path.exists(invoice_path):
        inv = _read_csv(invoice_path)
        req_inv = ["External ID", "Date", "Period", "Type", "Subtotal 1", "Currency"]
        missing_inv = [c for c in req_inv if c not in inv.columns]
        if missing_inv:
            print(f"[CW] InvoiceSearchCommissions.csv missing columns: {missing_inv} — all forecast")
            inv = pd.DataFrame()
        else:
            inv["External ID"] = inv["External ID"].astype(str).str.strip()
            inv["Period_ts"]   = inv["Period"].apply(_parse_period)
            inv["Date_ts"]     = pd.to_datetime(
                inv["Date"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce"
            )
            inv["amount_raw"]  = inv["Subtotal 1"].apply(_parse_subtotal)
            inv["currency"]    = inv["Currency"].astype(str).str.strip().str.upper()

            # Credit Memos → negative amount (clawback)
            is_credit = inv["Type"].astype(str).str.strip().str.lower() == "credit memo"
            inv.loc[is_credit, "amount_raw"] = -inv.loc[is_credit, "amount_raw"].abs()
    else:
        print("[CW] InvoiceSearchCommissions.csv not found — all forecast")
        inv = pd.DataFrame()

    matched_opp_ids: set[str] = set(inv["External ID"].unique()) if not inv.empty else set()

    # ------------------------------------------------------------------
    # 6a. MATCHED deals: one row per invoice / credit-memo
    #     acv_eur = calculated 1st-year ACV × invoice fraction of deal ACV
    #
    #     For credit memos: acv_eur is negative (clawback).
    #     We use the invoice Subtotal to determine what fraction of the
    #     deal ACV this invoice represents, then apply that to 1st-year ACV.
    #     If the deal total invoice amount is known, we scale proportionally;
    #     otherwise we pass the raw EUR invoice amount as-is.
    # ------------------------------------------------------------------
    if not inv.empty:
        inv_merged = inv.merge(
            opps[["opportunity_id", "opportunity_name", "employee_id",
                  "sao_type", "acv_eur", "close_date"]],
            left_on="External ID",
            right_on="opportunity_id",
            how="inner",
        )

        # Calculate total invoiced amount per opp (for proportional split)
        inv_totals = (
            inv_merged.groupby("opportunity_id")["amount_raw"]
            .sum()
            .rename("total_invoiced")
        )
        inv_merged = inv_merged.join(inv_totals, on="opportunity_id")

        for _, r in inv_merged.iterrows():
            period_ts  = r["Period_ts"]
            invoice_dt = r["Date_ts"] if pd.notna(r["Date_ts"]) else period_ts
            if pd.isna(period_ts):
                period_ts = invoice_dt
            if pd.isna(period_ts):
                continue

            # Determine commission ACV for this invoice row.
            # Scale 1st-year ACV by the invoice's share of total invoiced amount.
            inv_currency   = r["currency"]
            amount_local   = r["amount_raw"]
            total_invoiced = r.get("total_invoiced", amount_local) or amount_local

            # Convert invoice amount to EUR for proportional calculation
            fx_month = period_ts.to_period("M").to_timestamp()
            if inv_currency != "EUR":
                fx_rate = _get_fx_to_eur(fx_rates, fx_month, inv_currency)
                amount_eur_inv = amount_local / fx_rate if fx_rate != 0 else amount_local
                total_eur_inv  = total_invoiced / fx_rate if fx_rate != 0 else total_invoiced
            else:
                amount_eur_inv = amount_local
                total_eur_inv  = total_invoiced

            deal_acv_eur = float(r["acv_eur"])
            if total_eur_inv != 0 and deal_acv_eur > 0:
                # Proportional: this invoice's share of 1st-year ACV
                commission_acv = deal_acv_eur * (amount_eur_inv / total_eur_inv)
            else:
                # Fallback: use raw EUR invoice amount
                commission_acv = amount_eur_inv

            rows.append({
                "employee_id":      r["employee_id"],
                "opportunity_id":   r["opportunity_id"],
                "opportunity_name": r.get("opportunity_name", r["opportunity_id"]),
                "sao_type":         r["sao_type"],
                "acv_eur":          round(commission_acv, 2),
                "invoice_date":     invoice_dt,
                "month":            period_ts.to_period("M").to_timestamp(),
                "close_date":       r["close_date"],
                "is_forecast":      False,
                "document_number":  str(r.get("Document Number", "")).strip(),
                "invoice_currency": inv_currency,
            })

    # ------------------------------------------------------------------
    # 6b. UNMATCHED deals: forecast using 1st-year ACV + Close Date
    # ------------------------------------------------------------------
    unmatched  = opps[~opps["opportunity_id"].isin(matched_opp_ids)]
    forecast_count = 0

    for _, r in unmatched.iterrows():
        close_dt = r["close_date"]
        rows.append({
            "employee_id":      r["employee_id"],
            "opportunity_id":   r["opportunity_id"],
            "opportunity_name": r.get("opportunity_name", r["opportunity_id"]),
            "sao_type":         r["sao_type"],
            "acv_eur":          round(float(r["acv_eur"]), 2),
            "invoice_date":     close_dt,
            "month":            close_dt.to_period("M").to_timestamp(),
            "close_date":       close_dt,
            "is_forecast":      True,
            "document_number":  "",
            "invoice_currency": "EUR",
        })
        forecast_count += 1

    actual_count = len(rows) - forecast_count
    print(f"[CW] Invoice rows: {actual_count}, Forecast rows: {forecast_count}")

    if not rows:
        return _empty_df()

    result = pd.DataFrame(rows)
    result = result.dropna(subset=["month"])
    return result.reset_index(drop=True)


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "employee_id", "opportunity_id", "opportunity_name", "sao_type", "acv_eur",
        "invoice_date", "month", "close_date",
        "is_forecast", "document_number", "invoice_currency",
    ])


def _empty_ae_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "employee_id", "opportunity_id", "opportunity_name", "acv_eur",
        "multi_year_acv_eur", "invoice_date", "month", "close_date",
        "is_forecast", "document_number", "invoice_currency", "invoicing_cadence",
    ])


# ---------------------------------------------------------------------------
# AE closed-won builder
# ---------------------------------------------------------------------------

def build_ae_closed_won_commission(
    data_dir: str,
    employees: pd.DataFrame,
    fx_rates: pd.DataFrame,
) -> pd.DataFrame:
    """Return a normalised closed_won DataFrame for AE commission plans.

    Uses the 'Opportunity Owner' field from InputData.csv to match AEs.
    Adds multi_year_acv_eur: the ACV for year 2+ of multi-year deals.
    Both acv_eur (1st-year) and multi_year_acv_eur are in EUR.
    Note: commission % (10% base / 1% multi-year) is applied in ae.py.
    """
    input_path   = os.path.join(data_dir, "InputData.csv")
    invoice_path = os.path.join(data_dir, "InvoiceSearchCommissions.csv")

    if not os.path.exists(input_path):
        print("[AE CW] InputData.csv not found — AE closed won skipped")
        return _empty_ae_df()

    # ------------------------------------------------------------------
    # 1. Load InputData.csv
    # ------------------------------------------------------------------
    raw = _read_csv(input_path)

    required = ["Opportunity Id Casesafe", "Stage", "Opportunity Owner", "Lead Source",
                "Close Date", "Product Code", "Start Date", "End Date",
                "Price (converted)", "Duration (years)", "Quantity"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        print(f"[AE CW] InputData.csv missing columns: {missing} — skipped")
        return _empty_ae_df()

    # Filter to Closed Won + New Business with a non-blank Opportunity Owner
    raw = raw[
        (raw["Stage"].str.strip().str.lower() == "closed won") &
        (raw["Type"].str.strip().str.lower() == "new business") &
        (raw["Opportunity Owner"].notna()) &
        (raw["Opportunity Owner"].astype(str).str.strip() != "")
    ].copy()

    if raw.empty:
        print("[AE CW] No Closed Won New Business rows with Opportunity Owner found")
        return _empty_ae_df()

    # Parse line-level dates and numerics (same as SDR builder)
    raw["line_start"] = pd.to_datetime(raw["Start Date"].astype(str).str.strip(),
                                        format="%d/%m/%Y", errors="coerce")
    raw["line_end"]   = pd.to_datetime(raw["End Date"].astype(str).str.strip(),
                                        format="%d/%m/%Y", errors="coerce")
    raw["Price (converted)"] = pd.to_numeric(
        raw["Price (converted)"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0.0)
    raw["Duration (years)"] = pd.to_numeric(raw["Duration (years)"], errors="coerce").fillna(1.0)
    raw["Quantity"]         = pd.to_numeric(raw["Quantity"], errors="coerce").fillna(1.0)

    # ------------------------------------------------------------------
    # 2. Calculate 1st-year and total ACV per opportunity
    # ------------------------------------------------------------------
    first_year_acv: dict[str, float] = {}
    total_acv:      dict[str, float] = {}

    for opp_id, grp in raw.groupby("Opportunity Id Casesafe"):
        key = str(opp_id).strip()
        fy  = _calc_first_year_acv(grp)
        tot = _calc_total_rr_acv(grp)
        first_year_acv[key] = fy
        total_acv[key]      = tot

    # ------------------------------------------------------------------
    # 3. Build opportunity-level summary
    # ------------------------------------------------------------------
    has_cadence = "Invoicing Cadence" in raw.columns
    opp_cols = ["Opportunity Id Casesafe", "Opportunity Name", "Opportunity Owner",
                "Lead Source", "Close Date"] + (["Invoicing Cadence"] if has_cadence else [])
    opps = (
        raw[opp_cols]
        .drop_duplicates(subset=["Opportunity Id Casesafe"])
        .copy()
    )

    opps["close_date"] = pd.to_datetime(
        opps["Close Date"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce"
    )
    opps = opps.dropna(subset=["close_date"])

    # Exclude deals closed in 2025 or before — tracked separately
    opps = opps[opps["close_date"].dt.year >= 2026].copy()
    if opps.empty:
        print("[AE CW] No 2026+ Closed Won deals found")
        return _empty_ae_df()

    opps["invoicing_cadence"] = opps["Invoicing Cadence"].astype(str) if has_cadence else "yearly in advance"

    opps["opportunity_id"]   = opps["Opportunity Id Casesafe"].astype(str).str.strip()
    opps["opportunity_name"] = (
        opps["Opportunity Name"].astype(str).str.strip()
        if "Opportunity Name" in opps.columns
        else opps["opportunity_id"]
    )
    opps["acv_eur"]           = opps["opportunity_id"].map(first_year_acv).fillna(0.0)
    opps["total_rr_acv_eur"]  = opps["opportunity_id"].map(total_acv).fillna(0.0)
    opps["multi_year_acv_eur"] = (opps["total_rr_acv_eur"] - opps["acv_eur"]).clip(lower=0.0)

    # ------------------------------------------------------------------
    # 4. Match Opportunity Owner name → AE employee_id
    # ------------------------------------------------------------------
    ae_emps = employees[employees["role"] == "ae"][["employee_id", "name"]].copy()
    ae_emps["name_lower"] = ae_emps["name"].str.strip().str.lower()
    opps["_owner_lower"] = opps["Opportunity Owner"].astype(str).str.strip().str.lower()

    # Exact match first
    opps = opps.merge(
        ae_emps[["employee_id", "name_lower"]],
        left_on="_owner_lower",
        right_on="name_lower",
        how="inner",
    ).drop(columns=["_owner_lower", "name_lower"])

    if opps.empty:
        print("[AE CW] No Opportunity Owner names matched AE employees — skipped")
        return _empty_ae_df()

    n_opps = opps["opportunity_id"].nunique()
    n_with_acv = (opps["acv_eur"] > 0).sum()
    print(f"[AE CW] {n_opps} Closed Won deals matched to AEs "
          f"({n_with_acv} with 1st-year ACV > 0 from RR lines)")

    # ------------------------------------------------------------------
    # 5. Load InvoiceSearchCommissions.csv
    # ------------------------------------------------------------------
    rows = []

    if os.path.exists(invoice_path):
        inv = _read_csv(invoice_path)
        req_inv = ["External ID", "Date", "Period", "Type", "Subtotal 1", "Currency"]
        missing_inv = [c for c in req_inv if c not in inv.columns]
        if missing_inv:
            print(f"[AE CW] InvoiceSearchCommissions.csv missing columns: {missing_inv} — all forecast")
            inv = pd.DataFrame()
        else:
            inv["External ID"] = inv["External ID"].astype(str).str.strip()
            inv["Period_ts"]   = inv["Period"].apply(_parse_period)
            inv["Date_ts"]     = pd.to_datetime(
                inv["Date"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce"
            )
            inv["amount_raw"]  = inv["Subtotal 1"].apply(_parse_subtotal)
            inv["currency"]    = inv["Currency"].astype(str).str.strip().str.upper()
            is_credit = inv["Type"].astype(str).str.strip().str.lower() == "credit memo"
            inv.loc[is_credit, "amount_raw"] = -inv.loc[is_credit, "amount_raw"].abs()
    else:
        print("[AE CW] InvoiceSearchCommissions.csv not found — all forecast")
        inv = pd.DataFrame()

    matched_opp_ids: set[str] = set(inv["External ID"].unique()) if not inv.empty else set()

    # ------------------------------------------------------------------
    # 6a. MATCHED deals: proportional split by invoice amount
    # ------------------------------------------------------------------
    if not inv.empty:
        inv_merged = inv.merge(
            opps[["opportunity_id", "opportunity_name", "employee_id",
                  "acv_eur", "multi_year_acv_eur", "close_date", "invoicing_cadence"]],
            left_on="External ID",
            right_on="opportunity_id",
            how="inner",
        )

        inv_totals = (
            inv_merged.groupby("opportunity_id")["amount_raw"]
            .sum()
            .rename("total_invoiced")
        )
        inv_merged = inv_merged.join(inv_totals, on="opportunity_id")

        # First invoice date per opportunity — multi-year ACV booked here in full
        first_inv_period = inv_merged.groupby("opportunity_id")["Period_ts"].min()

        for _, r in inv_merged.iterrows():
            period_ts  = r["Period_ts"]
            invoice_dt = r["Date_ts"] if pd.notna(r["Date_ts"]) else period_ts
            if pd.isna(period_ts):
                period_ts = invoice_dt
            if pd.isna(period_ts):
                continue

            inv_currency   = r["currency"]
            amount_local   = r["amount_raw"]
            total_invoiced = r.get("total_invoiced", amount_local) or amount_local

            fx_month = period_ts.to_period("M").to_timestamp()
            if inv_currency != "EUR":
                fx_rate = _get_fx_to_eur(fx_rates, fx_month, inv_currency)
                amount_eur_inv = amount_local / fx_rate if fx_rate != 0 else amount_local
                total_eur_inv  = total_invoiced / fx_rate if fx_rate != 0 else total_invoiced
            else:
                amount_eur_inv = amount_local
                total_eur_inv  = total_invoiced

            deal_acv_fy = float(r["acv_eur"])
            deal_acv_my = float(r["multi_year_acv_eur"])

            if total_eur_inv != 0 and deal_acv_fy > 0:
                proportion = amount_eur_inv / total_eur_inv
                commission_acv_fy = deal_acv_fy * proportion
            else:
                commission_acv_fy = amount_eur_inv

            # Multi-year ACV commission paid in full on the first invoice only
            is_first = (period_ts == first_inv_period.get(r["opportunity_id"]))
            commission_acv_my = deal_acv_my if is_first else 0.0

            rows.append({
                "employee_id":       r["employee_id"],
                "opportunity_id":    r["opportunity_id"],
                "opportunity_name":  r.get("opportunity_name", r["opportunity_id"]),
                "acv_eur":           round(commission_acv_fy, 2),
                "multi_year_acv_eur": round(commission_acv_my, 2),
                "invoice_date":      invoice_dt,
                "month":             period_ts.to_period("M").to_timestamp(),
                "close_date":        r["close_date"],
                "is_forecast":       False,
                "document_number":   str(r.get("Document Number", "")).strip(),
                "invoice_currency":  inv_currency,
                "invoicing_cadence": r.get("invoicing_cadence", ""),
            })

    # ------------------------------------------------------------------
    # 6b. UNMATCHED deals: forecast rows, split by invoicing cadence
    # ------------------------------------------------------------------
    unmatched = opps[~opps["opportunity_id"].isin(matched_opp_ids)]
    forecast_count = 0

    for _, r in unmatched.iterrows():
        close_dt  = r["close_date"]
        acv_fy    = float(r["acv_eur"])
        acv_my    = float(r["multi_year_acv_eur"])
        cadence   = r.get("invoicing_cadence", "yearly in advance")
        n         = _cadence_n_invoices(cadence)
        months_between = 12 // n   # months between invoices

        acv_fy_per = round(acv_fy / n, 2)

        for i in range(n):
            inv_month = (close_dt + pd.DateOffset(months=months_between * i)).to_period("M").to_timestamp()
            rows.append({
                "employee_id":        r["employee_id"],
                "opportunity_id":     r["opportunity_id"],
                "opportunity_name":   r.get("opportunity_name", r["opportunity_id"]),
                "acv_eur":            acv_fy_per,
                # Multi-year ACV paid in full on the first invoice only
                "multi_year_acv_eur": round(acv_my, 2) if i == 0 else 0.0,
                "invoice_date":       inv_month,
                "month":              inv_month,
                "close_date":         close_dt,
                "is_forecast":        True,
                "document_number":    "",
                "invoice_currency":   "EUR",
                "invoicing_cadence":  cadence,
            })
            forecast_count += 1

    actual_count = len(rows) - forecast_count
    print(f"[AE CW] Invoice rows: {actual_count}, Forecast rows: {forecast_count}")

    if not rows:
        return _empty_ae_df()

    result = pd.DataFrame(rows)
    result = result.dropna(subset=["month"])
    return result.reset_index(drop=True)
