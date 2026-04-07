import os
import pandas as pd


def _read(path: str, required_cols: list[str]) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required data file not found: {path}")
    df = pd.read_csv(path, encoding="utf-8")
    df.columns = df.columns.str.strip()
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{os.path.basename(path)} is missing columns: {missing}")
    return df


def load_employees(data_dir: str) -> pd.DataFrame:
    df = _read(
        os.path.join(data_dir, "employees.csv"),
        ["employee_id", "name", "title", "role", "region", "country",
         "currency", "manager_id", "email", "plan_start_date", "plan_end_date"],
    )
    df["plan_start_date"] = pd.to_datetime(df["plan_start_date"], errors="coerce")
    df["plan_end_date"] = pd.to_datetime(df["plan_end_date"], errors="coerce")
    df["manager_id"] = df["manager_id"].fillna("")
    df["email"] = df["email"].fillna("")
    return df


def load_sdr_activities(data_dir: str) -> pd.DataFrame:
    df = _read(
        os.path.join(data_dir, "sdr_activities.csv"),
        ["date", "employee_id", "opportunity_id", "sao_type", "stage"],
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["sao_type"] = df["sao_type"].str.strip().str.lower()
    df["stage"] = df["stage"].str.strip().str.lower()
    # Only SAO-stage rows count
    df = df[df["stage"] == "sao"].copy()
    return df


def load_closed_won(data_dir: str) -> pd.DataFrame:
    df = _read(
        os.path.join(data_dir, "closed_won.csv"),
        ["close_date", "invoice_date", "employee_id", "opportunity_id", "sao_type", "acv_eur"],
    )
    df["close_date"] = pd.to_datetime(df["close_date"], errors="coerce")
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    df = df.dropna(subset=["invoice_date"])
    # Commission triggers on invoice month
    df["month"] = df["invoice_date"].dt.to_period("M").dt.to_timestamp()
    df["sao_type"] = df["sao_type"].str.strip().str.lower()
    df["acv_eur"] = pd.to_numeric(df["acv_eur"], errors="coerce").fillna(0)
    return df


def load_fx_rates(data_dir: str) -> pd.DataFrame:
    df = _read(
        os.path.join(data_dir, "fx_rates.csv"),
        ["month", "EUR_SEK", "EUR_GBP"],
    )
    df["month"] = pd.to_datetime(df["month"], errors="coerce")
    for col in ["EUR_SEK", "EUR_GBP"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "EUR_USD" not in df.columns:
        df["EUR_USD"] = 1.0
    else:
        df["EUR_USD"] = pd.to_numeric(df["EUR_USD"], errors="coerce").fillna(1.0)
    # EUR to EUR is always 1.0
    df["EUR_EUR"] = 1.0
    return df.dropna(subset=["month"])


def load_all(data_dir: str) -> dict:
    return {
        "employees": load_employees(data_dir),
        "sdr_activities": load_sdr_activities(data_dir),
        "closed_won": load_closed_won(data_dir),
        "fx_rates": load_fx_rates(data_dir),
    }
