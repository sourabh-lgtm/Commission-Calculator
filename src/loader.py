import os
import pandas as pd


def _read(path: str, required_cols: list[str], encoding: str = "utf-8") -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required data file not found: {path}")
    # Try supplied encoding, fall back to cp1252 for Salesforce exports
    for enc in [encoding, "cp1252", "utf-8-sig", "latin-1"]:
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Cannot decode {os.path.basename(path)} — try saving as UTF-8")
    df.columns = df.columns.str.strip()
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{os.path.basename(path)} is missing columns: {missing}")
    return df


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

def load_employees(data_dir: str) -> pd.DataFrame:
    df = _read(
        os.path.join(data_dir, "employees.csv"),
        ["employee_id", "name", "title", "role", "region", "country",
         "currency", "manager_id", "email", "plan_start_date", "plan_end_date"],
    )
    df["plan_start_date"] = pd.to_datetime(df["plan_start_date"], errors="coerce")
    df["plan_end_date"]   = pd.to_datetime(df["plan_end_date"],   errors="coerce")
    df["manager_id"] = df["manager_id"].fillna("")
    df["email"]      = df["email"].fillna("")
    return df


# ---------------------------------------------------------------------------
# SAO Commission Data  (replaces sdr_activities.csv)
#
# Source: Salesforce CRM export ("SAO_commission_data.csv")
# Key columns:
#   SDR            — SDR name; blank rows are ignored
#   DCT Discovery  — date of SAO (format: DD/MM/YYYY, HH:MM); used as commission month
#   Account Name   — used for 6-month deduplication
#   Lead Source    — "Outbound - *" → outbound, "Inbound - *" → inbound
#   Opportunity Name — used as opportunity identifier
# ---------------------------------------------------------------------------

_LEAD_SOURCE_MAP = {
    "outbound - sdr": "outbound",
    "outbound - ae":  "outbound",
    "outbound - mdr": "outbound",
    "outbound - cs":  "outbound",
    "inbound - marketing": "inbound",
    "inbound - product":   "inbound",
    "inbound - web":       "inbound",
    "inbound - referral":  "inbound",
}


def _classify_lead_source(val: str) -> str | None:
    """Return 'outbound', 'inbound', or None (skip) for a Lead Source value."""
    v = str(val).strip().lower()
    if v in _LEAD_SOURCE_MAP:
        return _LEAD_SOURCE_MAP[v]
    if v.startswith("outbound"):
        return "outbound"
    if v.startswith("inbound"):
        return "inbound"
    if v == "" or v == "nan":
        return None   # blank lead source — skip
    return None


def load_sao_commission_data(data_dir: str, employees: pd.DataFrame) -> pd.DataFrame:
    """Load SAO_commission_data.csv and return a normalised DataFrame.

    Transformations applied:
      1. Drop rows where SDR column is blank.
      2. Parse DCT Discovery date (DD/MM/YYYY, HH:MM).
      3. Drop rows with no valid discovery date.
      4. Classify Lead Source → sao_type (outbound / inbound); drop unknown.
      5. Match SDR name → employee_id via employees DataFrame.
      6. Drop rows where SDR name cannot be matched to an employee.
      7. Apply 6-month account deduplication: for each Account Name,
         only the first SAO within any 6-month rolling window qualifies.
         Subsequent SAOs for the same account within 6 months are excluded.
    """
    path = os.path.join(data_dir, "SAO_commission_data.csv")
    df = _read(path, ["SDR", "DCT Discovery", "Account Name", "Lead Source", "Opportunity Name"])

    # --- 1. Drop blank SDR rows ---
    df = df[df["SDR"].str.strip() != ""].copy()
    if df.empty:
        return _empty_sao_df()

    # --- 2. Parse discovery date ---
    df["date"] = pd.to_datetime(
        df["DCT Discovery"].str.strip(),
        format="%d/%m/%Y, %H:%M",
        errors="coerce",
    )

    # --- 3. Drop rows with no valid date ---
    df = df.dropna(subset=["date"]).copy()
    if df.empty:
        return _empty_sao_df()

    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()

    # --- 4. Classify lead source ---
    df["sao_type"] = df["Lead Source"].apply(_classify_lead_source)
    df = df[df["sao_type"].notna()].copy()
    if df.empty:
        return _empty_sao_df()

    # --- 5. Match SDR name → employee_id ---
    sdr_employees = employees[employees["role"] == "sdr"][["employee_id", "name"]].copy()
    # Case-insensitive match
    sdr_employees["name_lower"] = sdr_employees["name"].str.strip().str.lower()
    df["_sdr_lower"] = df["SDR"].str.strip().str.lower()
    df = df.merge(
        sdr_employees[["employee_id", "name_lower"]],
        left_on="_sdr_lower",
        right_on="name_lower",
        how="inner",   # inner join drops unmatched SDR names
    ).drop(columns=["_sdr_lower", "name_lower"])

    if df.empty:
        print("[Loader] Warning: no SDR names in SAO_commission_data matched employees.csv")
        return _empty_sao_df()

    # --- 6. Build opportunity_id from Opportunity Name ---
    df["opportunity_id"] = df["Opportunity Name"].str.strip()

    # --- 7. Six-month account deduplication ---
    # Sort chronologically; for each account, mark rows where a prior SAO
    # exists within the past 6 months as non-qualifying.
    df = df.sort_values("date").reset_index(drop=True)

    qualifying = []
    # Track the most recent qualifying date per account (across ALL SDRs)
    last_qualifying: dict[str, pd.Timestamp] = {}

    for _, row in df.iterrows():
        acct     = str(row["Account Name"]).strip().lower()
        disc_dt  = row["date"]
        last_dt  = last_qualifying.get(acct)

        if last_dt is None:
            # First time this account appears — always qualifies
            qualifies = True
        else:
            months_since = (disc_dt - last_dt).days / 30.44
            qualifies = months_since >= 6   # at least 6 months since last qualifying SAO

        qualifying.append(qualifies)
        if qualifies:
            last_qualifying[acct] = disc_dt

    df["qualifies"] = qualifying
    excluded = (~df["qualifies"]).sum()
    if excluded:
        print(f"[Loader] 6-month deduplication: {excluded} SAO(s) excluded (same account within 6 months)")

    df = df[df["qualifies"]].copy()

    # --- Final: select and rename output columns ---
    result = df[[
        "date", "month", "employee_id", "opportunity_id",
        "sao_type", "Account Name",
    ]].rename(columns={"Account Name": "account_name"}).copy()

    result["stage"] = "sao"
    return result.reset_index(drop=True)


def _empty_sao_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "date", "month", "employee_id", "opportunity_id",
        "sao_type", "account_name", "stage",
    ])


# ---------------------------------------------------------------------------
# Closed Won  (built from InputData.csv + InvoiceSearchCommissions.csv)
# ---------------------------------------------------------------------------

def load_ae_closed_won(data_dir: str, employees: pd.DataFrame, fx_rates: pd.DataFrame) -> pd.DataFrame:
    """Build the AE closed_won commission table using 'Opportunity Owner' field."""
    from src.closed_won_commission import build_ae_closed_won_commission, _empty_ae_df
    input_path = os.path.join(data_dir, "InputData.csv")
    if os.path.exists(input_path):
        return build_ae_closed_won_commission(data_dir, employees, fx_rates)
    from src.closed_won_commission import _empty_ae_df
    return _empty_ae_df()


def load_closed_won(data_dir: str, employees: pd.DataFrame, fx_rates: pd.DataFrame) -> pd.DataFrame:
    """Build the closed_won commission table from Salesforce + NetSuite exports.

    Falls back to the legacy closed_won.csv if InputData.csv is absent.
    """
    from src.closed_won_commission import build_closed_won_commission
    input_path = os.path.join(data_dir, "InputData.csv")
    if os.path.exists(input_path):
        return build_closed_won_commission(data_dir, employees, fx_rates)

    # Legacy fallback
    legacy_path = os.path.join(data_dir, "closed_won.csv")
    if not os.path.exists(legacy_path):
        from src.closed_won_commission import _empty_df
        return _empty_df()

    df = _read(
        legacy_path,
        ["close_date", "invoice_date", "employee_id", "opportunity_id", "sao_type", "acv_eur"],
    )
    df["close_date"]   = pd.to_datetime(df["close_date"],   errors="coerce")
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    df = df.dropna(subset=["invoice_date"])
    df["month"]       = df["invoice_date"].dt.to_period("M").dt.to_timestamp()
    df["sao_type"]    = df["sao_type"].str.strip().str.lower()
    df["acv_eur"]     = pd.to_numeric(df["acv_eur"], errors="coerce").fillna(0)
    df["is_forecast"] = False
    df["document_number"]  = ""
    df["invoice_currency"] = "EUR"
    return df


# ---------------------------------------------------------------------------
# FX Rates
# ---------------------------------------------------------------------------

def load_fx_rates(data_dir: str) -> pd.DataFrame:
    df = _read(os.path.join(data_dir, "fx_rates.csv"), ["month", "EUR_SEK", "EUR_GBP"])
    df["month"] = pd.to_datetime(df["month"], errors="coerce")
    for col in ["EUR_SEK", "EUR_GBP"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "EUR_USD" not in df.columns:
        df["EUR_USD"] = 1.0
    else:
        df["EUR_USD"] = pd.to_numeric(df["EUR_USD"], errors="coerce").fillna(1.0)
    df["EUR_EUR"] = 1.0
    return df.dropna(subset=["month"])


# ---------------------------------------------------------------------------
# Load all
# ---------------------------------------------------------------------------

def load_all(data_dir: str) -> dict:
    # Prefer Humaans export if present; fall back to hand-maintained employees.csv
    humaans_path = os.path.join(data_dir, "humaans_export.csv")
    if os.path.exists(humaans_path):
        from src.humaans_loader import load_humaans
        employees, salary_history = load_humaans(data_dir)
    else:
        employees      = load_employees(data_dir)
        salary_history = _empty_salary_history()

    fx_rates = load_fx_rates(data_dir)

    ae_cw = load_ae_closed_won(data_dir, employees, fx_rates)

    # Load AE and SDR Lead targets
    ae_targets       = _load_optional_csv(data_dir, "ae_targets.csv")
    sdr_lead_targets = _load_optional_csv(data_dir, "sdr_lead_targets.csv")

    return {
        "employees":        employees,
        "salary_history":   salary_history,
        "sdr_activities":   load_sao_commission_data(data_dir, employees),
        "closed_won":       load_closed_won(data_dir, employees, fx_rates),
        "ae_closed_won":    ae_cw,
        "ae_targets":       ae_targets,
        "sdr_lead_targets": sdr_lead_targets,
        "fx_rates":         fx_rates,
    }


def _load_optional_csv(data_dir: str, filename: str) -> "pd.DataFrame":
    """Load a CSV file if it exists; return empty DataFrame otherwise."""
    path = os.path.join(data_dir, filename)
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    if "employee_id" in df.columns:
        df["employee_id"] = df["employee_id"].astype(str).str.strip()
    return df


def _empty_salary_history() -> "pd.DataFrame":
    return pd.DataFrame(columns=[
        "employee_id", "effective_date", "end_date",
        "salary_monthly", "salary_currency", "title_at_time", "role_at_time",
    ])
