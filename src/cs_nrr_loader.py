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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (nrr_df, breakdown_df).

    nrr_df columns     : employee_id, year, quarter, nrr_pct
    breakdown_df columns: employee_id, year, quarter, account_id, account_name,
                          base_arr, add_on, upsell_downsell, churn

    Computes NRR for each CSA found in cs_book_of_business.csv.
    breakdown_df contains one row per account that had InputData activity in the
    period; accounts with no transactions are omitted (they contribute only to the
    base-ARR denominator).

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

    _empty_nrr = pd.DataFrame(columns=["employee_id", "year", "quarter", "nrr_pct", "total_arr", "nrr_numerator"])
    _empty_bkd = pd.DataFrame(columns=[
        "employee_id", "year", "quarter", "account_id", "account_name",
        "base_arr", "add_on", "one_off", "upsell_downsell", "churn",
    ])

    if not os.path.exists(bob_path):
        print("[NRR] cs_book_of_business.csv not found — skipping NRR computation.")
        return _empty_nrr, _empty_bkd

    if not os.path.exists(input_path):
        print("[NRR] InputData.csv not found — skipping NRR computation.")
        return _empty_nrr, _empty_bkd

    # ---- Load Book of Business ----
    bob = _read_csv(bob_path)

    # Required columns by index
    arr_col  = bob.columns[9]   # Flat Renewal ACV (converted)
    id_col   = bob.columns[11]  # Account ID
    csa_col  = bob.columns[19]  # CSA 2026
    name_col = bob.columns[5]   # Account Name

    renewal_date_col = bob.columns[12]  # "Renewal Date"

    bob["_account_id_15"] = bob[id_col].astype(str).str.strip().str[:15]
    bob["_csa_name"]      = bob[csa_col].astype(str).str.strip()
    bob["_account_name"]  = bob[name_col].astype(str).str.strip()
    bob["_renewal_date"]  = pd.to_datetime(
        bob[renewal_date_col].astype(str), format="%d/%m/%Y", errors="coerce"
    )
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

    # Per-account renewal date lookup (take first non-null date per account)
    acct_renewal: dict[str, pd.Timestamp | None] = {
        acct_id: (grp_acct["_renewal_date"].dropna().iloc[0]
                  if not grp_acct["_renewal_date"].dropna().empty else None)
        for acct_id, grp_acct in bob.groupby("_account_id_15")
    }

    # ---- Load InputData ----
    inp = _read_csv(input_path)

    inp["_account_id_15"] = inp["Account Id Casesafe"].astype(str).str.strip().str[:15]
    inp["_type"]          = inp["Type"].astype(str).str.strip()
    inp["_stage"]         = inp["Stage"].astype(str).str.strip()
    inp["_attainment"]    = pd.to_numeric(inp["Attainment New ACV (converted)"], errors="coerce").fillna(0)
    inp["_nr_tcv"]        = pd.to_numeric(
        inp.get("Non-Recurring TCV (converted)", pd.Series(dtype=str)),
        errors="coerce",
    ).fillna(0)
    inp["_close_date"]    = pd.to_datetime(inp["Close Date"], format="%d/%m/%Y", errors="coerce")

    # Deduplicate by Opportunity Id — keep one row per opp (product lines inflate counts)
    inp_dedup = (
        inp.dropna(subset=["_close_date"])
           .drop_duplicates(subset=["Opportunity Id Casesafe"])
           .copy()
    )

    # ---- Build name → employee_id map (with last-name fallback) ----
    cs_emps = employees_df[employees_df["role"].isin(["cs", "cs_lead"])][["employee_id", "name"]].copy()
    cs_emps["_name_lower"]     = cs_emps["name"].str.strip().str.lower()
    cs_emps["_last_name_lower"] = cs_emps["_name_lower"].str.split().str[-1]

    # Primary: exact full-name match
    name_to_id: dict[str, str] = {
        row["_name_lower"]: row["employee_id"]
        for _, row in cs_emps.iterrows()
    }
    # Fallback: last-name match (only registered if unique — avoids false matches)
    last_name_counts = cs_emps["_last_name_lower"].value_counts()
    last_name_to_id: dict[str, str] = {
        row["_last_name_lower"]: row["employee_id"]
        for _, row in cs_emps.iterrows()
        if last_name_counts[row["_last_name_lower"]] == 1
    }

    def _resolve_name(name: str) -> str | None:
        lower = name.strip().lower()
        if lower in name_to_id:
            return name_to_id[lower]
        last = lower.split()[-1]
        if last in last_name_to_id:
            matched_emp = cs_emps[cs_emps["_last_name_lower"] == last]["name"].iloc[0]
            print(f"[NRR] Name alias: '{name}' -> '{matched_emp}'")
            return last_name_to_id[last]
        return None

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
    results:   list[dict] = []
    breakdown: list[dict] = []

    # Build a lookup: account_id_15 → account_name (from BoB)
    acct_name_map: dict[str, str] = (
        bob.drop_duplicates(subset=["_account_id_15"])
           .set_index("_account_id_15")["_account_name"]
           .to_dict()
    )

    for csa_name, grp in bob.groupby("_csa_name"):
        emp_id = _resolve_name(csa_name)
        if emp_id is None:
            print(f"[NRR] Warning: CSA '{csa_name}' not found in employees — skipping.")
            continue

        total_arr = grp["_arr"].sum()
        if total_arr <= 0:
            print(f"[NRR] Warning: {csa_name} has total ARR = {total_arr:.0f} — skipping.")
            continue

        # Account IDs for this CSA (15-char), with per-account base ARR
        acct_arr: dict[str, float] = (
            grp.groupby("_account_id_15")["_arr"].sum().to_dict()
        )
        csa_account_ids = set(acct_arr.keys())

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
            one_off       = inp_q[inp_q["_type"] == "Add-On"]["_nr_tcv"].sum() * 0.5
            upsell_down   = inp_q[
                (inp_q["_type"] == "Renewal") & (inp_q["_stage"] != "Closed Lost")
            ]["_attainment"].sum()
            churn         = inp_q[
                (inp_q["_type"] == "Renewal") & (inp_q["_stage"] == "Closed Lost")
            ]["_attainment"].sum()

            # ---- Synthetic churn: contracts expired in YTD window with no renewal record ----
            inp_q_renewal_accts = set(inp_q[inp_q["_type"] == "Renewal"]["_account_id_15"].tolist())
            synth_churns: dict[str, float] = {}
            for acct_id, arr in acct_arr.items():
                rd = acct_renewal.get(acct_id)
                if rd is None or pd.isna(rd):
                    continue
                if not (ytd_start <= rd <= q_end):
                    continue
                if acct_id in inp_q_renewal_accts:
                    continue  # Already has a real renewal/churn record
                synth_churns[acct_id] = -arr
                print(
                    f"[NRR] Synthetic churn: {csa_name} "
                    f"{acct_name_map.get(acct_id, acct_id)} "
                    f"Q{qt} {yr}  renewal_date={rd.date()}  ARR={arr:,.0f}"
                )
            churn += sum(synth_churns.values())

            nrr_numerator = total_arr + add_ons + one_off + upsell_down + churn
            nrr_pct       = round((nrr_numerator / total_arr) * 100, 4)

            print(
                f"[NRR] {csa_name} Q{qt} {yr}: "
                f"ARR={total_arr:,.0f}  addon={add_ons:,.0f}  one_off={one_off:,.0f}  "
                f"upsell/down={upsell_down:,.0f}  churn={churn:,.0f}  "
                f"NRR={nrr_pct:.2f}%"
            )

            results.append({
                "employee_id":   emp_id,
                "year":          yr,
                "quarter":       qt,
                "nrr_pct":       nrr_pct,
                "total_arr":     total_arr,
                "nrr_numerator": nrr_numerator,
            })

            # ---- Per-account breakdown (accounts with activity or synthetic churn) ----
            for acct_id, base_arr in sorted(acct_arr.items(), key=lambda x: -x[1]):
                acct_q = inp_q[inp_q["_account_id_15"] == acct_id]
                acct_addon   = acct_q[acct_q["_type"] == "Add-On"]["_attainment"].sum()
                acct_one_off = acct_q[acct_q["_type"] == "Add-On"]["_nr_tcv"].sum() * 0.5
                acct_upsell  = acct_q[
                    (acct_q["_type"] == "Renewal") & (acct_q["_stage"] != "Closed Lost")
                ]["_attainment"].sum()
                acct_churn   = acct_q[
                    (acct_q["_type"] == "Renewal") & (acct_q["_stage"] == "Closed Lost")
                ]["_attainment"].sum()

                # Add synthetic churn if this account had no renewal record
                if acct_id in synth_churns:
                    acct_churn += synth_churns[acct_id]

                # Only include accounts that had some activity or synthetic churn
                if acct_addon == 0 and acct_one_off == 0 and acct_upsell == 0 and acct_churn == 0:
                    continue

                breakdown.append({
                    "employee_id":    emp_id,
                    "year":           yr,
                    "quarter":        qt,
                    "account_id":     acct_id,
                    "account_name":   acct_name_map.get(acct_id, acct_id),
                    "base_arr":       base_arr,
                    "add_on":         acct_addon,
                    "one_off":        acct_one_off,
                    "upsell_downsell": acct_upsell,
                    "churn":          acct_churn,
                })

    if not results:
        return _empty_nrr, _empty_bkd

    return pd.DataFrame(results), pd.DataFrame(breakdown) if breakdown else _empty_bkd


# ---------------------------------------------------------------------------
# CS Team Lead — aggregate NRR across entire team
# ---------------------------------------------------------------------------

def compute_cs_lead_nrr(
    data_dir: str,
    employees_df: pd.DataFrame,
    year: int | None = None,
    quarter: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute aggregate NRR for CS Team Leads (Delphine, Johnny).

    For each cs_lead employee, pools ALL accounts from their team members'
    (manager_id = lead.employee_id) books of business plus the lead's own
    accounts (if any), and computes NRR on the combined pool.

    Returns (nrr_df, breakdown_df) with the team lead's employee_id as key,
    ready to be appended to the individual CSA nrr tables.
    """
    _empty_nrr = pd.DataFrame(columns=["employee_id", "year", "quarter", "nrr_pct", "total_arr", "nrr_numerator"])
    _empty_bkd = pd.DataFrame(columns=[
        "employee_id", "year", "quarter", "account_id", "account_name",
        "base_arr", "add_on", "one_off", "upsell_downsell", "churn",
    ])

    leads = employees_df[employees_df["role"] == "cs_lead"]
    if leads.empty:
        return _empty_nrr, _empty_bkd

    bob_path   = os.path.join(data_dir, "cs_book_of_business.csv")
    input_path = os.path.join(data_dir, "InputData.csv")
    if not os.path.exists(bob_path) or not os.path.exists(input_path):
        return _empty_nrr, _empty_bkd

    bob = _read_csv(bob_path)
    arr_col  = bob.columns[9]   # Flat Renewal ACV (converted)
    id_col   = bob.columns[11]  # Account ID
    csa_col  = bob.columns[19]  # CSA 2026
    name_col = bob.columns[5]   # Account Name

    renewal_date_col_lead = bob.columns[12]  # "Renewal Date"

    bob["_account_id_15"] = bob[id_col].astype(str).str.strip().str[:15]
    bob["_csa_name"]      = bob[csa_col].astype(str).str.strip()
    bob["_account_name"]  = bob[name_col].astype(str).str.strip()
    bob["_renewal_date"]  = pd.to_datetime(
        bob[renewal_date_col_lead].astype(str), format="%d/%m/%Y", errors="coerce"
    )
    bob["_arr"]           = pd.to_numeric(
        bob[arr_col].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)
    bob = bob[
        (bob["_csa_name"] != "") & (bob["_csa_name"] != "nan") &
        (bob["_account_id_15"] != "") & (bob["_account_id_15"] != "nan")
    ].copy()

    inp = _read_csv(input_path)
    inp["_account_id_15"] = inp["Account Id Casesafe"].astype(str).str.strip().str[:15]
    inp["_type"]          = inp["Type"].astype(str).str.strip()
    inp["_stage"]         = inp["Stage"].astype(str).str.strip()
    inp["_attainment"]    = pd.to_numeric(inp["Attainment New ACV (converted)"], errors="coerce").fillna(0)
    inp["_nr_tcv"]        = pd.to_numeric(
        inp.get("Non-Recurring TCV (converted)", pd.Series(dtype=str)),
        errors="coerce",
    ).fillna(0)
    inp["_close_date"]    = pd.to_datetime(inp["Close Date"], format="%d/%m/%Y", errors="coerce")
    inp_dedup = (
        inp.dropna(subset=["_close_date"])
           .drop_duplicates(subset=["Opportunity Id Casesafe"])
           .copy()
    )

    # Name → employee_id for all CS/cs_lead employees (for BoB name matching)
    all_cs = employees_df[employees_df["role"].isin(["cs", "cs_lead"])][["employee_id", "name"]].copy()
    all_cs["_name_lower"]      = all_cs["name"].str.strip().str.lower()
    all_cs["_last_name_lower"] = all_cs["_name_lower"].str.split().str[-1]
    name_to_id: dict[str, str] = {r["_name_lower"]: r["employee_id"] for _, r in all_cs.iterrows()}
    last_counts = all_cs["_last_name_lower"].value_counts()
    last_name_to_id: dict[str, str] = {
        r["_last_name_lower"]: r["employee_id"]
        for _, r in all_cs.iterrows()
        if last_counts[r["_last_name_lower"]] == 1
    }
    id_to_name_lower: dict[str, str] = {r["employee_id"]: r["_name_lower"] for _, r in all_cs.iterrows()}

    # Determine year-quarter pairs
    if year is not None and quarter is not None:
        yq_pairs = [(year, quarter)]
    else:
        inp_dedup["_year"]    = inp_dedup["_close_date"].dt.year
        inp_dedup["_quarter"] = (inp_dedup["_close_date"].dt.month - 1) // 3 + 1
        yq_pairs = list(
            inp_dedup[inp_dedup["_year"] >= 2026][["_year", "_quarter"]]
            .drop_duplicates().sort_values(["_year", "_quarter"])
            .itertuples(index=False, name=None)
        )

    if not yq_pairs:
        return _empty_nrr, _empty_bkd

    acct_name_map: dict[str, str] = (
        bob.drop_duplicates(subset=["_account_id_15"])
           .set_index("_account_id_15")["_account_name"]
           .to_dict()
    )

    results:   list[dict] = []
    breakdown: list[dict] = []

    for _, lead in leads.iterrows():
        lead_id = lead["employee_id"]

        # All team member IDs (direct reports + lead's own accounts)
        team_ids = set(
            employees_df[employees_df["manager_id"] == lead_id]["employee_id"].tolist()
        ) | {lead_id}

        # Convert IDs → BoB CSA names
        team_names_lower = {id_to_name_lower[i] for i in team_ids if i in id_to_name_lower}

        # Pool team BoB rows
        def _bob_name_matches(csa_name: str) -> bool:
            lower = csa_name.strip().lower()
            if lower in team_names_lower:
                return True
            # Last-name fallback
            last = lower.split()[-1] if lower else ""
            matched_id = last_name_to_id.get(last)
            return matched_id in team_ids if matched_id else False

        team_bob = bob[bob["_csa_name"].apply(_bob_name_matches)].copy()
        if team_bob.empty:
            print(f"[NRR Lead] {lead['name']} ({lead_id}): no BoB accounts found — skipping.")
            continue

        total_arr = team_bob["_arr"].sum()
        if total_arr <= 0:
            print(f"[NRR Lead] {lead['name']} ({lead_id}): total ARR = 0 — skipping.")
            continue

        acct_arr: dict[str, float] = team_bob.groupby("_account_id_15")["_arr"].sum().to_dict()
        acct_ids = set(acct_arr.keys())
        inp_team = inp_dedup[inp_dedup["_account_id_15"].isin(acct_ids)].copy()

        # Per-account renewal date lookup for this team's accounts
        acct_renewal_lead: dict[str, pd.Timestamp | None] = {
            acct_id: (grp_a["_renewal_date"].dropna().iloc[0]
                      if not grp_a["_renewal_date"].dropna().empty else None)
            for acct_id, grp_a in team_bob.groupby("_account_id_15")
        }

        for yr, qt in yq_pairs:
            ytd_start, _ = _quarter_range(yr, 1)
            _, q_end     = _quarter_range(yr, qt)
            inp_q = inp_team[
                (inp_team["_close_date"] >= ytd_start) &
                (inp_team["_close_date"] <= q_end)
            ].copy()

            add_ons     = inp_q[inp_q["_type"] == "Add-On"]["_attainment"].sum()
            one_off     = inp_q[inp_q["_type"] == "Add-On"]["_nr_tcv"].sum() * 0.5
            upsell_down = inp_q[
                (inp_q["_type"] == "Renewal") & (inp_q["_stage"] != "Closed Lost")
            ]["_attainment"].sum()
            churn       = inp_q[
                (inp_q["_type"] == "Renewal") & (inp_q["_stage"] == "Closed Lost")
            ]["_attainment"].sum()

            # ---- Synthetic churn: contracts expired in YTD window with no renewal record ----
            inp_q_renewal_accts = set(inp_q[inp_q["_type"] == "Renewal"]["_account_id_15"].tolist())
            synth_churns_lead: dict[str, float] = {}
            for acct_id, arr in acct_arr.items():
                rd = acct_renewal_lead.get(acct_id)
                if rd is None or pd.isna(rd):
                    continue
                if not (ytd_start <= rd <= q_end):
                    continue
                if acct_id in inp_q_renewal_accts:
                    continue  # Already has a real renewal/churn record
                synth_churns_lead[acct_id] = -arr
                print(
                    f"[NRR Lead] Synthetic churn: {lead['name']} "
                    f"{acct_name_map.get(acct_id, acct_id)} "
                    f"Q{qt} {yr}  renewal_date={rd.date()}  ARR={arr:,.0f}"
                )
            churn += sum(synth_churns_lead.values())

            nrr_numerator = total_arr + add_ons + one_off + upsell_down + churn
            nrr_pct       = round((nrr_numerator / total_arr) * 100, 4)

            print(
                f"[NRR Lead] {lead['name']} Q{qt} {yr}: "
                f"TeamARR={total_arr:,.0f}  addon={add_ons:,.0f}  one_off={one_off:,.0f}  "
                f"upsell/down={upsell_down:,.0f}  churn={churn:,.0f}  NRR={nrr_pct:.2f}%"
            )

            results.append({"employee_id": lead_id, "year": yr, "quarter": qt, "nrr_pct": nrr_pct, "total_arr": total_arr, "nrr_numerator": nrr_numerator})

            for acct_id, base_arr in sorted(acct_arr.items(), key=lambda x: -x[1]):
                acct_q       = inp_q[inp_q["_account_id_15"] == acct_id]
                acct_addon   = acct_q[acct_q["_type"] == "Add-On"]["_attainment"].sum()
                acct_one_off = acct_q[acct_q["_type"] == "Add-On"]["_nr_tcv"].sum() * 0.5
                acct_upsell  = acct_q[
                    (acct_q["_type"] == "Renewal") & (acct_q["_stage"] != "Closed Lost")
                ]["_attainment"].sum()
                acct_churn   = acct_q[
                    (acct_q["_type"] == "Renewal") & (acct_q["_stage"] == "Closed Lost")
                ]["_attainment"].sum()

                # Add synthetic churn if this account had no renewal record
                if acct_id in synth_churns_lead:
                    acct_churn += synth_churns_lead[acct_id]

                if acct_addon == 0 and acct_one_off == 0 and acct_upsell == 0 and acct_churn == 0:
                    continue

                breakdown.append({
                    "employee_id":    lead_id,
                    "year":           yr,
                    "quarter":        qt,
                    "account_id":     acct_id,
                    "account_name":   acct_name_map.get(acct_id, acct_id),
                    "base_arr":       base_arr,
                    "add_on":         acct_addon,
                    "one_off":        acct_one_off,
                    "upsell_downsell": acct_upsell,
                    "churn":          acct_churn,
                })

    if not results:
        return _empty_nrr, _empty_bkd

    nrr_df = pd.DataFrame(results)
    bkd_df = pd.DataFrame(breakdown) if breakdown else _empty_bkd
    return nrr_df, bkd_df


# ---------------------------------------------------------------------------
# CS Team Lead — multi-year ACV commission
# ---------------------------------------------------------------------------

def compute_cs_lead_multi_year_acv(
    data_dir: str,
    employees_df: pd.DataFrame,
) -> pd.DataFrame:
    """Find renewal deals with multi-year contracts from the team leads' BoB.

    For each renewal opportunity whose Account ID is in a team lead's team BoB
    and whose contract duration > 12 months, computes the multi-year ACV in EUR.

    multi_year_acv_eur = max(0, Recurring TCV (converted) - Flat Renewal ACV (converted))
    Fallback (if TCV missing): Flat Renewal ACV × (duration_years - 1)

    Note: Break-clause data is not available in InputData; this logic ignores
    break clauses. Deals with break clauses should be reviewed manually.

    Returns DataFrame: employee_id, month, opportunity_id, opportunity_name,
                       acv_eur (multi-year portion), contract_years
    """
    empty = pd.DataFrame(columns=[
        "employee_id", "month", "opportunity_id", "opportunity_name",
        "acv_eur", "contract_years",
    ])

    leads = employees_df[employees_df["role"] == "cs_lead"]
    if leads.empty:
        return empty

    bob_path   = os.path.join(data_dir, "cs_book_of_business.csv")
    input_path = os.path.join(data_dir, "InputData.csv")
    if not os.path.exists(bob_path) or not os.path.exists(input_path):
        return empty

    bob = _read_csv(bob_path)
    arr_col  = bob.columns[9]   # Flat Renewal ACV (converted)
    id_col   = bob.columns[11]  # Account ID
    csa_col  = bob.columns[19]  # CSA 2026

    bob["_account_id_15"] = bob[id_col].astype(str).str.strip().str[:15]
    bob["_csa_name"]      = bob[csa_col].astype(str).str.strip()
    bob["_arr"]           = pd.to_numeric(
        bob[arr_col].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)
    bob = bob[(bob["_csa_name"] != "") & (bob["_csa_name"] != "nan")].copy()

    # Per-account base ARR map (15-char ID → EUR ARR)
    acct_arr_map: dict[str, float] = (
        bob.drop_duplicates(subset=["_account_id_15"])
           .set_index("_account_id_15")["_arr"]
           .to_dict()
    )
    # CSA name → 15-char account IDs
    csa_to_accounts: dict[str, set[str]] = {}
    for _, r in bob.iterrows():
        csa_to_accounts.setdefault(r["_csa_name"].strip().lower(), set()).add(r["_account_id_15"])

    # All CS employee name lookup
    all_cs = employees_df[employees_df["role"].isin(["cs", "cs_lead"])][["employee_id", "name"]].copy()
    all_cs["_name_lower"]      = all_cs["name"].str.strip().str.lower()
    all_cs["_last_name_lower"] = all_cs["_name_lower"].str.split().str[-1]
    id_to_name_lower: dict[str, str] = {r["employee_id"]: r["_name_lower"] for _, r in all_cs.iterrows()}
    last_counts = all_cs["_last_name_lower"].value_counts()
    last_name_to_id: dict[str, str] = {
        r["_last_name_lower"]: r["employee_id"]
        for _, r in all_cs.iterrows()
        if last_counts[r["_last_name_lower"]] == 1
    }
    # Set of all CS employee names (lower) — used to gate multi-year ACV by opp ownership
    cs_names_lower: set[str] = set(all_cs["_name_lower"].tolist())

    # Load InputData — renewal deals with contract date info
    inp = _read_csv(input_path)
    inp["_account_id_15"]   = inp["Account Id Casesafe"].astype(str).str.strip().str[:15]
    inp["_type"]            = inp["Type"].astype(str).str.strip()
    inp["_stage"]           = inp["Stage"].astype(str).str.strip()
    inp["_close_date"]      = pd.to_datetime(inp["Close Date"], format="%d/%m/%Y", errors="coerce")
    inp["_contract_start"]  = pd.to_datetime(inp.get("Contract Start Date", pd.Series(dtype=str)), format="%d/%m/%Y", errors="coerce")
    inp["_contract_end"]    = pd.to_datetime(inp.get("Contract End Date",   pd.Series(dtype=str)), format="%d/%m/%Y", errors="coerce")
    inp["_flat_acv"]        = pd.to_numeric(inp.get("Flat Renewal ACV (converted)", pd.Series(dtype=str)), errors="coerce").fillna(0)
    inp["_tcv"]             = pd.to_numeric(inp.get("Recurring TCV (converted)",    pd.Series(dtype=str)), errors="coerce").fillna(0)
    inp["_opp_name"]        = inp["Opportunity Name"].astype(str).str.strip()
    inp["_opp_owner_lower"] = inp["Opportunity Owner"].astype(str).str.strip().str.lower()

    # Only include renewals where the Opportunity Owner is a CS employee.
    # This ensures AMs/AEs who own deals in a CSA's book do not generate
    # multi-year ACV commission for the CS lead.
    renewals = (
        inp[
            (inp["_type"] == "Renewal") &
            (inp["_stage"] != "Closed Lost") &
            inp["_close_date"].notna() &
            inp["_contract_start"].notna() &
            inp["_contract_end"].notna() &
            inp["_opp_owner_lower"].isin(cs_names_lower)
        ]
        .drop_duplicates(subset=["Opportunity Id Casesafe"])
        .copy()
    )
    if renewals.empty:
        return empty

    renewals["_duration_years"] = (
        (renewals["_contract_end"] - renewals["_contract_start"]).dt.days / 365.25
    )
    renewals["_month"] = renewals["_close_date"].dt.to_period("M").dt.to_timestamp()

    rows: list[dict] = []

    for _, lead in leads.iterrows():
        lead_id        = lead["employee_id"]
        lead_name_lower = id_to_name_lower.get(lead_id, "")

        # Only accounts owned directly by the team lead (not the whole team)
        own_acct_ids: set[str] = set()
        for csa_lower, acct_set in csa_to_accounts.items():
            if csa_lower == lead_name_lower:
                own_acct_ids.update(acct_set)
            elif lead_name_lower:
                # Last-name fallback
                lead_last = lead_name_lower.split()[-1]
                csa_last  = csa_lower.split()[-1] if csa_lower else ""
                if csa_last and csa_last == lead_last:
                    own_acct_ids.update(acct_set)

        if not own_acct_ids:
            continue

        team_renewals = renewals[
            (renewals["_account_id_15"].isin(own_acct_ids)) &
            (renewals["_duration_years"] > 1.0)
        ].copy()

        for _, r in team_renewals.iterrows():
            flat_acv = float(r["_flat_acv"])
            tcv      = float(r["_tcv"])
            years    = float(r["_duration_years"])

            if tcv > flat_acv > 0:
                multi_year_acv = tcv - flat_acv
            elif flat_acv > 0:
                multi_year_acv = flat_acv * (years - 1)
            elif acct_arr_map.get(r["_account_id_15"], 0) > 0:
                multi_year_acv = acct_arr_map[r["_account_id_15"]] * (years - 1)
            else:
                continue

            if multi_year_acv <= 0:
                continue

            rows.append({
                "employee_id":      lead_id,
                "month":            r["_month"],
                "opportunity_id":   str(r["Opportunity Id Casesafe"]),
                "opportunity_name": r["_opp_name"],
                "acv_eur":          round(multi_year_acv, 2),
                "contract_years":   round(years, 2),
            })
            print(
                f"[MultiYr Lead] {lead['name']}: {r['_opp_name'][:40]} "
                f"{years:.1f}yr  multi_yr_acv_eur={multi_year_acv:,.0f}"
            )

    return pd.DataFrame(rows) if rows else empty


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
