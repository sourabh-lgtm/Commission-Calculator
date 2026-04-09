"""Load and process the Humaans HR export.

Produces two DataFrames:
  employees       — current state per employee (same schema as employees.csv)
  salary_history  — full salary timeline per employee (for prorated bonus calcs)
"""

import os
import pandas as pd


# ---------------------------------------------------------------------------
# Job title → commission role mapping
# Rules are applied in order; first match wins.
# Matching is case-insensitive substring.
# ---------------------------------------------------------------------------
_TITLE_RULES: list[tuple[str, str]] = [
    # SDR Lead (check before generic SDR to avoid overlap)
    ("sdr team lead",    "sdr_lead"),
    ("sdr lead",         "sdr_lead"),

    # SDR variants (check before "account" so "SDR" doesn't fall through)
    ("sales development representative", "sdr"),
    ("enterprise sales development",     "sdr"),

    # AE variants — check before "account manager" to avoid overlap;
    # "Nordic Sales Lead" and "Inside Sales Executive" are AE-equivalent roles
    ("enterprise account executive",  "ae"),
    ("mid-market account executive",  "ae"),
    ("midmarket account executive",   "ae"),
    ("account executive",             "ae"),
    ("nordic sales lead",             "ae"),
    ("inside sales executive",        "ae"),

    # AM variants
    ("senior account manager", "am"),
    ("account manager",        "am"),

    # CS Team Lead (check before generic "climate strategy" catch-all)
    ("climate strategy team lead",         "cs_lead"),

    # Climate Strategy variants (cs role — commissioned)
    # Check longer/more-specific titles first to avoid false matches
    ("lead climate strategy expert",       "cs"),
    ("senior climate strategy advisor",    "cs"),
    ("associate climate strategy advisor", "cs"),
    ("climate strategy advisor",           "cs"),
    ("climate strategy",                   "cs"),   # catch-all for future CS variants

    # Customer Success (no commission plan — remapped to avoid conflict with cs)
    ("senior customer success", "customer_success"),
    ("customer success",        "customer_success"),

    # Solutions Engineer
    ("senior solutions engineer", "se"),
    ("solutions engineer",        "se"),

    # Revenue / Sales leadership
    ("vp revenue",          "sales_director"),
    ("vp sales",            "sales_director"),
    ("head of sales",       "sales_director"),
    ("director of sales",   "sales_director"),
    ("chief revenue",       "sales_director"),

    # Finance leadership
    ("chief financial officer", "cfo"),
    ("cfo",                     "cfo"),

    # Revenue Operations (non-commissioned manager)
    ("revenue operations", "manager"),

    # General sales management — catch-all
    ("sales manager", "manager"),
]


def _determine_role(title) -> str:
    """Map a Humaans job title to an internal commission role. Returns 'other' if unmatched."""
    if not title or not isinstance(title, str):
        return "other"
    t = title.strip().lower()
    for keyword, role in _TITLE_RULES:
        if keyword in t:
            return role
    return "other"


# ---------------------------------------------------------------------------
# Country → (region, default_currency)
# Currency from the salary record takes priority; this is a fallback.
# ---------------------------------------------------------------------------
_COUNTRY_MAP: dict[str, tuple[str, str]] = {
    "sweden":         ("Nordics", "SEK"),
    "norway":         ("Nordics", "NOK"),
    "denmark":        ("Nordics", "DKK"),
    "finland":        ("Nordics", "EUR"),
    "united kingdom": ("UK",      "GBP"),
    "germany":        ("Europe",  "EUR"),
    "france":         ("Europe",  "EUR"),
    "netherlands":    ("Europe",  "EUR"),
    "belgium":        ("Europe",  "EUR"),
    "spain":          ("Europe",  "EUR"),
    "ireland":        ("Europe",  "EUR"),
    "united states":  ("Americas","USD"),
    "canada":         ("Americas","CAD"),
}


def _get_region(country: str) -> str:
    return _COUNTRY_MAP.get(country.strip().lower(), ("Other", "EUR"))[0]


def _normalize_to_monthly(amount: float, frequency: str) -> float:
    """Normalise any salary frequency to a monthly equivalent."""
    f = frequency.strip().lower()
    if f == "monthly":
        return amount
    if f == "annual":
        return amount / 12
    if f == "daily":
        return amount * 21.67   # ~21.67 working days/month
    return amount   # unknown — return as-is


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

HUMAANS_FILE = "humaans_export.csv"


def load_humaans(data_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load humaans_export.csv and return (employees_df, salary_history_df).

    employees_df columns:
        employee_id, name, title, role, region, country, currency,
        manager_id, email, plan_start_date, plan_end_date

    salary_history_df columns:
        employee_id, effective_date, end_date, salary_monthly,
        salary_currency, title_at_time
    """
    path = os.path.join(data_dir, HUMAANS_FILE)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Humaans export not found at '{path}'.\n"
            f"Export from Humaans and save as '{HUMAANS_FILE}' in the data/ folder."
        )

    # Try encodings — Humaans exports as UTF-8
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            raw = pd.read_csv(path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Cannot decode {HUMAANS_FILE}")

    raw.columns = raw.columns.str.strip()

    # Rename for convenience
    raw = raw.rename(columns={
        "First name":          "first_name",
        "Last name":           "last_name",
        "Work email":          "email",
        "Country":             "country",
        "Job title":           "title",
        "Department":          "department",
        "Manager":             "manager_name",
        "Manager email":       "manager_email",
        "Role effective date": "role_eff_date",
        "Employee ID":         "employee_id",
        "Employment start":    "employment_start",
        "Salary amount":       "salary_amount",
        "Salary currency":     "salary_currency",
        "Salary frequency":    "salary_frequency",
        "Salary effective date": "salary_eff_date",
        "Cost center - Code":  "cost_center_code",
    })

    # Parse dates
    for col in ("role_eff_date", "salary_eff_date", "employment_start"):
        raw[col] = pd.to_datetime(raw[col], errors="coerce")

    raw["salary_amount"] = pd.to_numeric(raw["salary_amount"], errors="coerce").fillna(0)
    raw["employee_id"]   = raw["employee_id"].astype(str).str.strip()
    raw["email"]         = raw["email"].str.strip().str.lower()
    raw["manager_email"] = raw["manager_email"].fillna("").str.strip().str.lower()

    # Build full name
    raw["name"] = (raw["first_name"].str.strip() + " " + raw["last_name"].str.strip()).str.strip()

    # Normalise salary to monthly
    raw["salary_monthly"] = raw.apply(
        lambda r: _normalize_to_monthly(r["salary_amount"], r.get("salary_frequency", "monthly")),
        axis=1,
    )

    # ------------------------------------------------------------------
    # Build email → employee_id map (for manager_id resolution)
    # ------------------------------------------------------------------
    email_to_id: dict[str, str] = {}
    for _, r in raw.iterrows():
        if r["email"]:
            email_to_id[r["email"]] = str(r["employee_id"])

    # ------------------------------------------------------------------
    # Process each employee
    # ------------------------------------------------------------------
    employees_rows: list[dict] = []
    salary_history_rows: list[dict] = []

    grouped = raw.groupby("employee_id", sort=False)

    for emp_id, grp in grouped:
        # --- Current role: row with latest role_eff_date ---
        latest_role_row = (
            grp.sort_values("role_eff_date", ascending=False).iloc[0]
        )
        title        = latest_role_row["title"]
        role         = _determine_role(title)
        country      = latest_role_row["country"]
        region       = _get_region(country)
        email        = latest_role_row["email"]
        name         = latest_role_row["name"]
        department        = latest_role_row.get("department", "")
        cost_center_code  = latest_role_row.get("cost_center_code", "")
        emp_start    = latest_role_row["employment_start"]
        manager_email = latest_role_row["manager_email"]
        manager_id   = email_to_id.get(manager_email, "")

        # --- Current salary: row with latest salary_eff_date ---
        latest_sal_row = (
            grp.dropna(subset=["salary_eff_date"])
               .sort_values("salary_eff_date", ascending=False)
               .iloc[0]
            if not grp.dropna(subset=["salary_eff_date"]).empty
            else latest_role_row
        )
        currency = latest_sal_row["salary_currency"].strip()

        # plan_start_date: the FIRST date this employee held the current commission role.
        # A later row for the same role (e.g. manager email change) must not push the date forward.
        # For a mid-tenure promotion (SDR → AM), this correctly gives the AM start date.
        current_role = role
        same_role_rows = grp[grp["title"].apply(_determine_role) == current_role]
        if not same_role_rows.empty:
            plan_start = same_role_rows["role_eff_date"].min()
        else:
            plan_start = latest_role_row["role_eff_date"] if pd.notna(latest_role_row["role_eff_date"]) else emp_start
        if pd.isna(plan_start):
            plan_start = emp_start
        plan_end = pd.Timestamp("2026-12-31")   # FY26

        employees_rows.append({
            "employee_id":       str(emp_id),
            "name":              name,
            "title":             title,
            "role":              role,
            "department":        department,
            "cost_center_code":  cost_center_code,
            "region":            region,
            "country":           country,
            "currency":          currency,
            "manager_id":        manager_id,
            "email":             email,
            "plan_start_date":   plan_start,
            "plan_end_date":     plan_end,
            "employment_start":  emp_start,
        })

        # --- Salary history: one record per unique salary_eff_date ---
        sal_rows = (
            grp.dropna(subset=["salary_eff_date"])
               .drop_duplicates(subset=["salary_eff_date"], keep="last")
               .sort_values("salary_eff_date")
        )

        sal_list = sal_rows.to_dict(orient="records")
        for i, s in enumerate(sal_list):
            eff   = s["salary_eff_date"]
            end   = sal_list[i + 1]["salary_eff_date"] - pd.Timedelta(days=1) if i + 1 < len(sal_list) else pd.NaT
            salary_history_rows.append({
                "employee_id":    str(emp_id),
                "effective_date": eff,
                "end_date":       end,
                "salary_monthly": _normalize_to_monthly(s["salary_amount"], s.get("salary_frequency", "monthly")),
                "salary_currency": s["salary_currency"].strip(),
                "title_at_time":  s["title"],
                "role_at_time":   _determine_role(s["title"]),
            })

    employees_df     = pd.DataFrame(employees_rows)
    salary_history_df = pd.DataFrame(salary_history_rows) if salary_history_rows else pd.DataFrame(
        columns=["employee_id","effective_date","end_date","salary_monthly","salary_currency","title_at_time","role_at_time"]
    )

    _log_summary(employees_df)
    return employees_df, salary_history_df


def _log_summary(df: pd.DataFrame):
    from collections import Counter
    role_counts = Counter(df["role"])
    commissioned = {k: v for k, v in role_counts.items() if k not in ("other",)}
    print(f"[Humaans] Loaded {len(df)} employees. Commission-eligible roles: {commissioned}")
