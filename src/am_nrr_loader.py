"""Calculate NRR for each AM from Book of Business + InputData.

NRR formula:
    NRR = (Add_Ons + One_Off_20pct + Upsell + Downsell + Churn + Total_ARR) / Total_ARR * 100

One-off services: 20% of Non-Recurring TCV on Add-On deals (per AM commission plan).

Book of Business file: data/am_book_of_business.csv
  Combined file with all AM accounts (one row per account per AM).
  Columns used:
  - Column J (index 9)  = "Flat Renewal ACV (converted)"  -- starting ARR per account
  - Column L (index 11) = "Account ID"                     -- 15-char Salesforce ID
  - Column M (index 12) = "Renewal Date"
  - Column S (index 18) = "Account Owner 2026"             -- AM name
  - Column F (index 5)  = "Account Name"

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
    start_month = (quarter - 1) * 3 + 1
    start = pd.Timestamp(year=year, month=start_month, day=1)
    end   = (start + pd.offsets.MonthEnd(3)).replace(hour=23, minute=59, second=59)
    return start, end


# ---------------------------------------------------------------------------
# Individual AM NRR
# ---------------------------------------------------------------------------

def compute_am_nrr(
    data_dir: str,
    employees_df: pd.DataFrame,
    year: int | None = None,
    quarter: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (nrr_df, breakdown_df) for individual AMs.

    Uses BoB column 18 (Account Owner 2026) for AM name.
    One-off services = 20% of Non-Recurring TCV (per AM commission plan).
    """
    bob_path   = os.path.join(data_dir, "am_book_of_business.csv")
    input_path = os.path.join(data_dir, "InputData.csv")

    _empty_nrr = pd.DataFrame(columns=["employee_id", "year", "quarter", "nrr_pct", "total_arr", "nrr_numerator"])
    _empty_bkd = pd.DataFrame(columns=[
        "employee_id", "year", "quarter", "account_id", "account_name",
        "base_arr", "add_on", "one_off", "upsell_downsell", "churn",
    ])

    if not os.path.exists(bob_path):
        print("[AM NRR] am_book_of_business.csv not found -- skipping.")
        return _empty_nrr, _empty_bkd
    if not os.path.exists(input_path):
        print("[AM NRR] InputData.csv not found -- skipping.")
        return _empty_nrr, _empty_bkd

    bob = _read_csv(bob_path)
    arr_col          = bob.columns[9]   # Flat Renewal ACV (converted)
    id_col           = bob.columns[11]  # Account ID
    am_col           = bob.columns[18]  # Account Owner 2026
    name_col         = bob.columns[5]   # Account Name
    renewal_date_col = bob.columns[12]  # Renewal Date

    bob["_account_id_15"] = bob[id_col].astype(str).str.strip().str[:15]
    bob["_am_name"]       = bob[am_col].astype(str).str.strip()
    bob["_account_name"]  = bob[name_col].astype(str).str.strip()
    bob["_renewal_date"]  = pd.to_datetime(
        bob[renewal_date_col].astype(str), format="%d/%m/%Y", errors="coerce"
    )
    bob["_arr"] = pd.to_numeric(
        bob[arr_col].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)

    # Keep only rows with a populated AM name and valid account ID
    bob = bob[
        (bob["_am_name"] != "") & (bob["_am_name"] != "nan") &
        (bob["_account_id_15"] != "") & (bob["_account_id_15"] != "nan")
    ].copy()

    acct_renewal: dict[str, pd.Timestamp | None] = {
        acct_id: (grp["_renewal_date"].dropna().iloc[0]
                  if not grp["_renewal_date"].dropna().empty else None)
        for acct_id, grp in bob.groupby("_account_id_15")
    }

    inp = _read_csv(input_path)
    inp["_account_id_15"] = inp["Account Id Casesafe"].astype(str).str.strip().str[:15]
    inp["_type"]          = inp["Type"].astype(str).str.strip()
    inp["_stage"]         = inp["Stage"].astype(str).str.strip()
    inp["_attainment"]    = pd.to_numeric(inp["Attainment New ACV (converted)"], errors="coerce").fillna(0)
    inp["_nr_tcv"]        = pd.to_numeric(
        inp.get("Non-Recurring TCV (converted)", pd.Series(dtype=str)),
        errors="coerce",
    ).fillna(0)
    inp["_close_date"]     = pd.to_datetime(inp["Close Date"], format="%d/%m/%Y", errors="coerce")
    inp["_contract_start"] = pd.to_datetime(
        inp.get("Contract Start Date", pd.Series(dtype=str)),
        format="%d/%m/%Y", errors="coerce",
    )
    inp_dedup = (
        inp.dropna(subset=["_close_date"])
           .drop_duplicates(subset=["Opportunity Id Casesafe"])
           .copy()
    )

    # Build name -> employee_id map for am / am_lead employees
    am_emps = employees_df[employees_df["role"].isin(["am", "am_lead"])][["employee_id", "name"]].copy()
    am_emps["_name_lower"]      = am_emps["name"].str.strip().str.lower()
    am_emps["_last_name_lower"] = am_emps["_name_lower"].str.split().str[-1]

    name_to_id: dict[str, str] = {r["_name_lower"]: r["employee_id"] for _, r in am_emps.iterrows()}
    last_counts = am_emps["_last_name_lower"].value_counts()
    last_name_to_id: dict[str, str] = {
        r["_last_name_lower"]: r["employee_id"]
        for _, r in am_emps.iterrows()
        if last_counts[r["_last_name_lower"]] == 1
    }
    # First-name fallback: useful when BoB only stores a first name (e.g. "Mathias")
    am_emps["_first_name_lower"] = am_emps["_name_lower"].str.split().str[0]
    first_counts = am_emps["_first_name_lower"].value_counts()
    first_name_to_id: dict[str, str] = {
        r["_first_name_lower"]: r["employee_id"]
        for _, r in am_emps.iterrows()
        if first_counts[r["_first_name_lower"]] == 1
    }

    def _resolve_name(name: str) -> str | None:
        lower = name.strip().lower()
        if lower in name_to_id:
            return name_to_id[lower]
        last = lower.split()[-1]
        if last in last_name_to_id:
            matched = am_emps[am_emps["_last_name_lower"] == last]["name"].iloc[0]
            print(f"[AM NRR] Name alias: '{name}' -> '{matched}'")
            return last_name_to_id[last]
        first = lower.split()[0]
        if first in first_name_to_id:
            matched = am_emps[am_emps["_first_name_lower"] == first]["name"].iloc[0]
            print(f"[AM NRR] First-name alias: '{name}' -> '{matched}'")
            return first_name_to_id[first]
        return None

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
        print("[AM NRR] No 2026 activity in InputData -- returning empty.")
        return _empty_nrr, _empty_bkd

    acct_name_map: dict[str, str] = (
        bob.drop_duplicates(subset=["_account_id_15"])
           .set_index("_account_id_15")["_account_name"]
           .to_dict()
    )

    results:   list[dict] = []
    breakdown: list[dict] = []

    for am_name, grp in bob.groupby("_am_name"):
        emp_id = _resolve_name(am_name)
        if emp_id is None:
            print(f"[AM NRR] Warning: AM '{am_name}' not found in employees -- skipping.")
            continue

        total_arr = grp["_arr"].sum()
        if total_arr <= 0:
            print(f"[AM NRR] Warning: {am_name} has total ARR = {total_arr:.0f} -- skipping.")
            continue

        acct_arr: dict[str, float] = grp.groupby("_account_id_15")["_arr"].sum().to_dict()
        csa_account_ids = set(acct_arr.keys())
        inp_am = inp_dedup[inp_dedup["_account_id_15"].isin(csa_account_ids)].copy()

        for yr, qt in yq_pairs:
            ytd_start, _ = _quarter_range(yr, 1)
            _, q_end     = _quarter_range(yr, qt)
            inp_q = inp_am[
                (inp_am["_close_date"] >= ytd_start) &
                (inp_am["_close_date"] <= q_end)
            ].copy()

            add_ons     = inp_q[inp_q["_type"] == "Add-On"]["_attainment"].sum()
            # One-off: 20% of Non-Recurring TCV (per AM commission plan)
            one_off     = inp_q[inp_q["_type"] == "Add-On"]["_nr_tcv"].sum() * 0.20
            upsell_down = inp_q[
                (inp_q["_type"] == "Renewal") & (inp_q["_stage"] != "Closed Lost")
            ]["_attainment"].sum()
            churn       = inp_q[
                (inp_q["_type"] == "Renewal") & (inp_q["_stage"] == "Closed Lost")
            ]["_attainment"].sum()

            # Synthetic churn: accounts with renewal date in YTD window but no renewal record
            am_renewals = inp_am[
                (inp_am["_type"] == "Renewal") &
                inp_am["_contract_start"].notna()
            ]
            acct_max_contract_start: dict[str, pd.Timestamp] = (
                am_renewals.groupby("_account_id_15")["_contract_start"].max().to_dict()
            )
            synth_churns: dict[str, float] = {}
            for acct_id, arr in acct_arr.items():
                rd = acct_renewal.get(acct_id)
                if rd is None or pd.isna(rd):
                    continue
                if not (ytd_start <= rd <= q_end):
                    continue
                max_cs = acct_max_contract_start.get(acct_id)
                if max_cs is not None and max_cs >= rd:
                    continue
                synth_churns[acct_id] = -arr
                print(
                    f"[AM NRR] Synthetic churn: {am_name} "
                    f"{acct_name_map.get(acct_id, acct_id)} "
                    f"Q{qt} {yr}  renewal_date={rd.date()}  ARR={arr:,.0f}"
                )
            churn += sum(synth_churns.values())

            nrr_numerator = total_arr + add_ons + one_off + upsell_down + churn
            nrr_pct       = round((nrr_numerator / total_arr) * 100, 4)

            print(
                f"[AM NRR] {am_name} Q{qt} {yr}: "
                f"ARR={total_arr:,.0f}  addon={add_ons:,.0f}  one_off={one_off:,.0f}  "
                f"upsell/down={upsell_down:,.0f}  churn={churn:,.0f}  NRR={nrr_pct:.2f}%"
            )

            results.append({
                "employee_id":   emp_id,
                "year":          yr,
                "quarter":       qt,
                "nrr_pct":       nrr_pct,
                "total_arr":     total_arr,
                "nrr_numerator": nrr_numerator,
            })

            for acct_id, base_arr in sorted(acct_arr.items(), key=lambda x: -x[1]):
                acct_q       = inp_q[inp_q["_account_id_15"] == acct_id]
                acct_addon   = acct_q[acct_q["_type"] == "Add-On"]["_attainment"].sum()
                acct_one_off = acct_q[acct_q["_type"] == "Add-On"]["_nr_tcv"].sum() * 0.20
                acct_upsell  = acct_q[
                    (acct_q["_type"] == "Renewal") & (acct_q["_stage"] != "Closed Lost")
                ]["_attainment"].sum()
                acct_churn   = acct_q[
                    (acct_q["_type"] == "Renewal") & (acct_q["_stage"] == "Closed Lost")
                ]["_attainment"].sum()
                if acct_id in synth_churns:
                    acct_churn += synth_churns[acct_id]
                if acct_addon == 0 and acct_one_off == 0 and acct_upsell == 0 and acct_churn == 0:
                    continue
                breakdown.append({
                    "employee_id":     emp_id,
                    "year":            yr,
                    "quarter":         qt,
                    "account_id":      acct_id,
                    "account_name":    acct_name_map.get(acct_id, acct_id),
                    "base_arr":        base_arr,
                    "add_on":          acct_addon,
                    "one_off":         acct_one_off,
                    "upsell_downsell": acct_upsell,
                    "churn":           acct_churn,
                })

    if not results:
        return _empty_nrr, _empty_bkd
    return pd.DataFrame(results), pd.DataFrame(breakdown) if breakdown else _empty_bkd


# ---------------------------------------------------------------------------
# AM Lead/Director -- aggregate NRR across entire AM team
# ---------------------------------------------------------------------------

def compute_am_lead_nrr(
    data_dir: str,
    employees_df: pd.DataFrame,
    year: int | None = None,
    quarter: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute aggregate NRR for AM Leads / Directors.

    Pools ALL accounts from ALL am employees' books and computes NRR on the
    combined portfolio, keyed by the lead's employee_id.

    Returns (nrr_df, breakdown_df) ready to be appended to the individual AM table.
    """
    _empty_nrr = pd.DataFrame(columns=["employee_id", "year", "quarter", "nrr_pct", "total_arr", "nrr_numerator"])
    _empty_bkd = pd.DataFrame(columns=[
        "employee_id", "year", "quarter", "account_id", "account_name",
        "base_arr", "add_on", "one_off", "upsell_downsell", "churn",
    ])

    leads = employees_df[employees_df["role"] == "am_lead"]
    if leads.empty:
        return _empty_nrr, _empty_bkd

    bob_path   = os.path.join(data_dir, "am_book_of_business.csv")
    input_path = os.path.join(data_dir, "InputData.csv")
    if not os.path.exists(bob_path) or not os.path.exists(input_path):
        return _empty_nrr, _empty_bkd

    bob = _read_csv(bob_path)
    arr_col          = bob.columns[9]
    id_col           = bob.columns[11]
    am_col           = bob.columns[18]  # Account Owner 2026
    name_col         = bob.columns[5]
    renewal_date_col = bob.columns[12]

    bob["_account_id_15"] = bob[id_col].astype(str).str.strip().str[:15]
    bob["_am_name"]       = bob[am_col].astype(str).str.strip()
    bob["_account_name"]  = bob[name_col].astype(str).str.strip()
    bob["_renewal_date"]  = pd.to_datetime(
        bob[renewal_date_col].astype(str), format="%d/%m/%Y", errors="coerce"
    )
    bob["_arr"] = pd.to_numeric(
        bob[arr_col].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)
    bob = bob[
        (bob["_am_name"] != "") & (bob["_am_name"] != "nan") &
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
    inp["_close_date"]     = pd.to_datetime(inp["Close Date"], format="%d/%m/%Y", errors="coerce")
    inp["_contract_start"] = pd.to_datetime(
        inp.get("Contract Start Date", pd.Series(dtype=str)),
        format="%d/%m/%Y", errors="coerce",
    )
    inp_dedup = (
        inp.dropna(subset=["_close_date"])
           .drop_duplicates(subset=["Opportunity Id Casesafe"])
           .copy()
    )

    # All AM employee names (am only, not leads -- leads have their own BoB if any)
    all_am = employees_df[employees_df["role"].isin(["am", "am_lead"])][["employee_id", "name"]].copy()
    all_am["_name_lower"]      = all_am["name"].str.strip().str.lower()
    all_am["_last_name_lower"] = all_am["_name_lower"].str.split().str[-1]
    id_to_name_lower: dict[str, str] = {r["employee_id"]: r["_name_lower"] for _, r in all_am.iterrows()}
    last_counts = all_am["_last_name_lower"].value_counts()
    last_name_to_id: dict[str, str] = {
        r["_last_name_lower"]: r["employee_id"]
        for _, r in all_am.iterrows()
        if last_counts[r["_last_name_lower"]] == 1
    }
    all_am_names_lower: set[str] = set(all_am["_name_lower"].tolist())

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

    def _am_name_matches(am_name: str) -> bool:
        lower = am_name.strip().lower()
        if lower in all_am_names_lower:
            return True
        last = lower.split()[-1] if lower else ""
        return last_name_to_id.get(last) is not None

    # Pool all AM accounts
    all_am_bob = bob[bob["_am_name"].apply(_am_name_matches)].copy()
    if all_am_bob.empty:
        print("[AM NRR Lead] No BoB accounts found for any AM -- skipping.")
        return _empty_nrr, _empty_bkd

    total_arr_all = all_am_bob["_arr"].sum()
    if total_arr_all <= 0:
        print("[AM NRR Lead] Total ARR = 0 -- skipping.")
        return _empty_nrr, _empty_bkd

    all_acct_arr: dict[str, float] = all_am_bob.groupby("_account_id_15")["_arr"].sum().to_dict()
    all_acct_ids = set(all_acct_arr.keys())
    inp_all = inp_dedup[inp_dedup["_account_id_15"].isin(all_acct_ids)].copy()

    acct_renewal_all: dict[str, pd.Timestamp | None] = {
        acct_id: (grp["_renewal_date"].dropna().iloc[0]
                  if not grp["_renewal_date"].dropna().empty else None)
        for acct_id, grp in all_am_bob.groupby("_account_id_15")
    }

    results:   list[dict] = []
    breakdown: list[dict] = []

    for _, lead in leads.iterrows():
        lead_id = lead["employee_id"]

        for yr, qt in yq_pairs:
            ytd_start, _ = _quarter_range(yr, 1)
            _, q_end     = _quarter_range(yr, qt)
            inp_q = inp_all[
                (inp_all["_close_date"] >= ytd_start) &
                (inp_all["_close_date"] <= q_end)
            ].copy()

            add_ons     = inp_q[inp_q["_type"] == "Add-On"]["_attainment"].sum()
            one_off     = inp_q[inp_q["_type"] == "Add-On"]["_nr_tcv"].sum() * 0.20
            upsell_down = inp_q[
                (inp_q["_type"] == "Renewal") & (inp_q["_stage"] != "Closed Lost")
            ]["_attainment"].sum()
            churn       = inp_q[
                (inp_q["_type"] == "Renewal") & (inp_q["_stage"] == "Closed Lost")
            ]["_attainment"].sum()

            all_renewals = inp_all[
                (inp_all["_type"] == "Renewal") &
                inp_all["_contract_start"].notna()
            ]
            acct_max_cs: dict[str, pd.Timestamp] = (
                all_renewals.groupby("_account_id_15")["_contract_start"].max().to_dict()
            )
            synth_churns: dict[str, float] = {}
            for acct_id, arr in all_acct_arr.items():
                rd = acct_renewal_all.get(acct_id)
                if rd is None or pd.isna(rd):
                    continue
                if not (ytd_start <= rd <= q_end):
                    continue
                if (acct_max_cs.get(acct_id) or pd.NaT) >= rd:
                    continue
                synth_churns[acct_id] = -arr
            churn += sum(synth_churns.values())

            nrr_numerator = total_arr_all + add_ons + one_off + upsell_down + churn
            nrr_pct       = round((nrr_numerator / total_arr_all) * 100, 4)

            print(
                f"[AM NRR Lead] {lead['name']} Q{qt} {yr}: "
                f"TeamARR={total_arr_all:,.0f}  addon={add_ons:,.0f}  one_off={one_off:,.0f}  "
                f"upsell/down={upsell_down:,.0f}  churn={churn:,.0f}  NRR={nrr_pct:.2f}%"
            )

            results.append({
                "employee_id":   lead_id,
                "year":          yr,
                "quarter":       qt,
                "nrr_pct":       nrr_pct,
                "total_arr":     total_arr_all,
                "nrr_numerator": nrr_numerator,
            })

            for acct_id, base_arr in sorted(all_acct_arr.items(), key=lambda x: -x[1]):
                acct_q       = inp_q[inp_q["_account_id_15"] == acct_id]
                acct_addon   = acct_q[acct_q["_type"] == "Add-On"]["_attainment"].sum()
                acct_one_off = acct_q[acct_q["_type"] == "Add-On"]["_nr_tcv"].sum() * 0.20
                acct_upsell  = acct_q[
                    (acct_q["_type"] == "Renewal") & (acct_q["_stage"] != "Closed Lost")
                ]["_attainment"].sum()
                acct_churn   = acct_q[
                    (acct_q["_type"] == "Renewal") & (acct_q["_stage"] == "Closed Lost")
                ]["_attainment"].sum()
                if acct_id in synth_churns:
                    acct_churn += synth_churns[acct_id]
                if acct_addon == 0 and acct_one_off == 0 and acct_upsell == 0 and acct_churn == 0:
                    continue
                breakdown.append({
                    "employee_id":     lead_id,
                    "year":            yr,
                    "quarter":         qt,
                    "account_id":      acct_id,
                    "account_name":    acct_name_map.get(acct_id, acct_id),
                    "base_arr":        base_arr,
                    "add_on":          acct_addon,
                    "one_off":         acct_one_off,
                    "upsell_downsell": acct_upsell,
                    "churn":           acct_churn,
                })

    if not results:
        return _empty_nrr, _empty_bkd
    return pd.DataFrame(results), pd.DataFrame(breakdown) if breakdown else _empty_bkd


# ---------------------------------------------------------------------------
# Multi-year ACV for all AM employees (individual + leads)
# ---------------------------------------------------------------------------

def compute_am_multi_year_acv(
    data_dir: str,
    employees_df: pd.DataFrame,
) -> pd.DataFrame:
    """Find renewal deals with multi-year contracts for all AM employees.

    For each renewal whose Account ID is in an AM's BoB and whose contract
    duration > 12 months, computes the multi-year ACV in EUR.

    multi_year_acv_eur = max(0, Recurring TCV - Flat Renewal ACV)
    Fallback: Flat Renewal ACV * (duration_years - 1)

    Returns DataFrame: employee_id, month, opportunity_id, opportunity_name,
                       acv_eur (multi-year portion), contract_years
    """
    empty = pd.DataFrame(columns=[
        "employee_id", "month", "opportunity_id", "opportunity_name",
        "acv_eur", "contract_years",
    ])

    am_employees = employees_df[employees_df["role"].isin(["am", "am_lead"])]
    if am_employees.empty:
        return empty

    bob_path   = os.path.join(data_dir, "am_book_of_business.csv")
    input_path = os.path.join(data_dir, "InputData.csv")
    if not os.path.exists(bob_path) or not os.path.exists(input_path):
        return empty

    bob = _read_csv(bob_path)
    arr_col = bob.columns[9]
    id_col  = bob.columns[11]
    am_col  = bob.columns[18]  # Account Owner 2026

    bob["_account_id_15"] = bob[id_col].astype(str).str.strip().str[:15]
    bob["_am_name"]       = bob[am_col].astype(str).str.strip()
    bob["_arr"]           = pd.to_numeric(
        bob[arr_col].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)
    bob = bob[(bob["_am_name"] != "") & (bob["_am_name"] != "nan")].copy()

    acct_arr_map: dict[str, float] = (
        bob.drop_duplicates(subset=["_account_id_15"])
           .set_index("_account_id_15")["_arr"]
           .to_dict()
    )
    am_to_accounts: dict[str, set[str]] = {}
    for _, r in bob.iterrows():
        am_to_accounts.setdefault(str(r["_am_name"]).strip().lower(), set()).add(r["_account_id_15"])

    # AM employee name lookup
    all_am = employees_df[employees_df["role"].isin(["am", "am_lead"])][["employee_id", "name"]].copy()
    all_am["_name_lower"]      = all_am["name"].str.strip().str.lower()
    all_am["_last_name_lower"] = all_am["_name_lower"].str.split().str[-1]
    id_to_name_lower: dict[str, str] = {r["employee_id"]: r["_name_lower"] for _, r in all_am.iterrows()}
    last_counts = all_am["_last_name_lower"].value_counts()
    am_names_lower: set[str] = set(all_am["_name_lower"].tolist())

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

    # Only renewals where the Opportunity Owner is an AM employee
    renewals = (
        inp[
            (inp["_type"] == "Renewal") &
            (inp["_stage"] != "Closed Lost") &
            inp["_close_date"].notna() &
            inp["_contract_start"].notna() &
            inp["_contract_end"].notna() &
            inp["_opp_owner_lower"].isin(am_names_lower)
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

    for _, am_emp in am_employees.iterrows():
        emp_id         = am_emp["employee_id"]
        am_name_lower  = id_to_name_lower.get(emp_id, "")
        if not am_name_lower:
            continue

        # Accounts owned by this AM (via BoB name match)
        own_acct_ids: set[str] = set()
        for bob_name_lower, acct_set in am_to_accounts.items():
            if bob_name_lower == am_name_lower:
                own_acct_ids.update(acct_set)
            elif am_name_lower:
                am_last   = am_name_lower.split()[-1]
                bob_last  = bob_name_lower.split()[-1] if bob_name_lower else ""
                if bob_last and bob_last == am_last and last_counts.get(am_last, 0) == 1:
                    own_acct_ids.update(acct_set)

        if not own_acct_ids:
            continue

        emp_renewals = renewals[
            (renewals["_account_id_15"].isin(own_acct_ids)) &
            (renewals["_duration_years"] > 1.0)
        ].copy()

        for _, r in emp_renewals.iterrows():
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
                "employee_id":      emp_id,
                "month":            r["_month"],
                "opportunity_id":   str(r["Opportunity Id Casesafe"]),
                "opportunity_name": r["_opp_name"],
                "acv_eur":          round(multi_year_acv, 2),
                "contract_years":   round(years, 2),
            })
            print(
                f"[AM MultiYr] {am_emp['name']}: {r['_opp_name'][:40]} "
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
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise ValueError(f"Could not read {path} with any supported encoding.")
