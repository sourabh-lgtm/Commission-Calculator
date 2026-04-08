"""Calculate NRR for each CSA from Book of Business + InputData.

NRR formula (from commission plan):
    NRR = (Add_Ons + Upsell + Downsell + Churn + Total_ARR) / Total_ARR * 100

Where from InputData (filtered to the year/quarter's close date range):
  - Opp Type = "Renewal", Stage != "Closed Lost":
      Attainment New ACV → Upsell/Downsell
  - Opp Type = "Add-On":
      Attainment New ACV → Add-Ons
  - Opp Type = "Renewal", Stage = "Closed Lost":
      Attainment New ACV → Churn (already negative in Salesforce export)

Book of Business CSV columns used:
  - Column J (index 9)  = "Flat Renewal ACV (converted)"  — starting ARR per account
  - Column L (index 11) = "Account ID"                     — 15-char Salesforce ID
  - Column T (index 19) = "CSA 2026"                       — CSA name

Account ID matching:
  The BoB uses 15-char Salesforce IDs; InputData uses 18-char IDs.
  We match on the first 15 characters.

Deduplication:
  InputData has one row per product line item; we deduplicate by
  Opportunity Id Casesafe before aggregating so multi-line deals
  are not double-counted.
"""

import os
import pandas as pd


# ---------------------------------------------------------------------------
# Quarter date ranges (inclusive)
# ---------------------------------------------------------------------------

def _quarter_range(year: int, quarter: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (start, end) timestamps for a year/quarter."""
    start_month = (quarter - 1) * 3 + 1
    end_month   = start_month + 2
    start = pd.Timestamp(year=year, month=start_month, day=1)
    end   = (start + pd.offsets.MonthEnd(3)).replace(hour=23, minute=59, second=59)
    return start, end


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

def compute_cs_nrr(
    data_dir: str,
    employees_df: pd.DataFrame,
    year: int | None = None,
    quarter: int | None = None,
) -> pd.DataFrame:
    """Return a DataFrame with columns: employee_id, year, quarter, nrr_pct.

    Computes NRR for each CSA found in cs_book_of_business.csv.
    If year/quarter are None, computes all year-quarter combinations
    found in InputData's Close Date for 2026.

    Parameters
    ----------
    data_dir     : path to the data/ directory
    employees_df : loaded employees DataFrame (from humaans or employees.csv)
    year         : restrict to a specific year (optional)
    quarter      : restrict to a specific quarter 1–4 (optional)
    """
    bob_path   = os.path.join(data_dir, "cs_book_of_business.csv")
    input_path = os.path.join(data_dir, "InputData.csv")

    if not os.path.exists(bob_path):
        print("[NRR] cs_book_of_business.csv not found — skipping NRR computation.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "nrr_pct"])

    if not os.path.exists(input_path):
        print("[NRR] InputData.csv not found — skipping NRR computation.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "nrr_pct"])

    # ---- Load Book of Business ----
    bob = _read_csv(bob_path)

    # Required columns by index
    arr_col = bob.columns[9]   # Flat Renewal ACV (converted)
    id_col  = bob.columns[11]  # Account ID
    csa_col = bob.columns[19]  # CSA 2026

    bob["_account_id_15"] = bob[id_col].astype(str).str.strip().str[:15]
    bob["_csa_name"]      = bob[csa_col].astype(str).str.strip()
    # Remove thousand-separator commas before numeric conversion
    bob["_arr"]           = pd.to_numeric(
        bob[arr_col].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)

    # Drop rows with no CSA name or blank account IDs
    bob = bob[
        (bob["_csa_name"] != "") &
        (bob["_csa_name"] != "nan") &
        (bob["_account_id_15"] != "") &
        (bob["_account_id_15"] != "nan")
    ].copy()

    # ---- Load InputData ----
    inp = _read_csv(input_path)

    inp["_account_id_15"] = inp["Account Id Casesafe"].astype(str).str.strip().str[:15]
    inp["_type"]          = inp["Type"].astype(str).str.strip()
    inp["_stage"]         = inp["Stage"].astype(str).str.strip()
    inp["_attainment"]    = pd.to_numeric(inp["Attainment New ACV (converted)"], errors="coerce").fillna(0)
    inp["_close_date"]    = pd.to_datetime(inp["Close Date"], format="%d/%m/%Y", errors="coerce")

    # Deduplicate by Opportunity Id — keep one row per opp (product lines inflate counts)
    inp_dedup = (
        inp.dropna(subset=["_close_date"])
           .drop_duplicates(subset=["Opportunity Id Casesafe"])
           .copy()
    )

    # ---- Build name → employee_id map ----
    cs_emps = employees_df[employees_df["role"] == "cs"][["employee_id", "name"]].copy()
    cs_emps["_name_lower"] = cs_emps["name"].str.strip().str.lower()
    name_to_id: dict[str, str] = {
        row["_name_lower"]: row["employee_id"]
        for _, row in cs_emps.iterrows()
    }

    # ---- Determine which year-quarters to compute ----
    if year is not None and quarter is not None:
        yq_pairs = [(year, quarter)]
    else:
        # All year-quarters in InputData (typically 2026 Q1, Q2, …)
        inp_dedup["_year"]    = inp_dedup["_close_date"].dt.year
        inp_dedup["_quarter"] = ((inp_dedup["_close_date"].dt.month - 1) // 3 + 1)
        yq_pairs = (
            inp_dedup[inp_dedup["_year"] >= 2026][["_year", "_quarter"]]
            .drop_duplicates()
            .sort_values(["_year", "_quarter"])
            .itertuples(index=False, name=None)
        )
        yq_pairs = list(yq_pairs)

    if not yq_pairs:
        print("[NRR] No 2026 activity found in InputData — returning empty NRR table.")
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "nrr_pct"])

    # ---- Compute NRR per CSA per year-quarter ----
    results: list[dict] = []

    for csa_name, grp in bob.groupby("_csa_name"):
        csa_lower = csa_name.lower()
        emp_id = name_to_id.get(csa_lower)
        if emp_id is None:
            print(f"[NRR] Warning: CSA '{csa_name}' not found in employees — skipping.")
            continue

        total_arr = grp["_arr"].sum()
        if total_arr <= 0:
            print(f"[NRR] Warning: {csa_name} has total ARR = {total_arr:.0f} — skipping.")
            continue

        # Account IDs for this CSA (15-char)
        csa_account_ids = set(grp["_account_id_15"].tolist())

        # Filter InputData to this CSA's accounts
        inp_csa = inp_dedup[inp_dedup["_account_id_15"].isin(csa_account_ids)].copy()

        for yr, qt in yq_pairs:
            # Cumulative YTD: from Jan 1 of the year through end of this quarter
            ytd_start, q_end = _quarter_range(yr, 1)
            _, q_end         = _quarter_range(yr, qt)
            inp_q = inp_csa[
                (inp_csa["_close_date"] >= ytd_start) &
                (inp_csa["_close_date"] <= q_end)
            ].copy()

            add_ons       = inp_q[inp_q["_type"] == "Add-On"]["_attainment"].sum()
            upsell_down   = inp_q[
                (inp_q["_type"] == "Renewal") & (inp_q["_stage"] != "Closed Lost")
            ]["_attainment"].sum()
            churn         = inp_q[
                (inp_q["_type"] == "Renewal") & (inp_q["_stage"] == "Closed Lost")
            ]["_attainment"].sum()

            nrr_numerator = total_arr + add_ons + upsell_down + churn
            nrr_pct       = round((nrr_numerator / total_arr) * 100, 4)

            print(
                f"[NRR] {csa_name} Q{qt} {yr}: "
                f"ARR={total_arr:,.0f}  addon={add_ons:,.0f}  "
                f"upsell/down={upsell_down:,.0f}  churn={churn:,.0f}  "
                f"NRR={nrr_pct:.2f}%"
            )

            results.append({
                "employee_id": emp_id,
                "year":        yr,
                "quarter":     qt,
                "nrr_pct":     nrr_pct,
            })

    if not results:
        return pd.DataFrame(columns=["employee_id", "year", "quarter", "nrr_pct"])

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _read_csv(path: str) -> pd.DataFrame:
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {os.path.basename(path)}")
