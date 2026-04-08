# Commission Calculator — Architecture & Codebase Reference

> Living document for onboarding future Claude sessions. Last updated: 2026-04-08. Changes: CS dashboard workings tab, role-specific PDF pages, accruals banding fix.

---

## What This App Does

Internal tool for **Normative** that calculates, reviews, approves, and distributes monthly sales commission statements. It ingests Salesforce CRM exports and Humaans HR data, runs them through a commission rules engine, and serves a web dashboard where finance can review numbers, approve them, and email PDF statements to each employee.

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | |
| Web server | `http.server.HTTPServer` (stdlib) | No Flask/FastAPI/Django. Hand-rolled. |
| Frontend | Vanilla JS + HTML string embedded in `launch.py` | Chart.js loaded from CDN. Single-page app. |
| Data processing | `pandas` + `numpy` | All computation in-memory |
| Excel export | `openpyxl` | Payroll + accruals workbooks |
| PDF generation | `reportlab` | Commission statement PDFs |
| Config | `config.ini` via `configparser` | SMTP, data dir, port |
| Dependencies | `requirements.txt` — only 4 packages | `pandas>=2.0`, `numpy>=1.24`, `openpyxl>=3.1`, `reportlab>=4.0` |

---

## Repository Layout

```
Commission Calculator/
├── launch.py                   # Entry point: HTTP server + all API route handlers + embedded HTML
├── export_excel.py             # Payroll and Finance Accruals Excel workbook builders
├── config.ini                  # SMTP + runtime config (gitignored)
├── requirements.txt
│
├── src/
│   ├── pipeline.py             # 6-stage orchestration; defines CommissionModel dataclass
│   ├── loader.py               # CSV loading, SAO deduplication, data routing
│   ├── humaans_loader.py       # Humaans HR export parser; job title → role mapping
│   ├── closed_won_commission.py# ACV commission calculation from InputData + NetSuite invoices
│   ├── reports.py              # All JSON report builder functions (called from API routes)
│   ├── spif.py                 # SPIF award calculation logic
│   ├── approval_state.py       # JSON-backed per-employee approval state machine
│   ├── pdf_generator.py        # ReportLab commission statement PDFs — role-specific pages
│   │                           #   generate_statement() dispatches on employee["role"]:
│   │                           #   CS → _cs_summary_page() + _cs_workings_page()
│   │                           #   SDR/AE/AM → _summary_page() + _workings_page()
│   ├── email_sender.py         # SMTP email dispatch (statements + Excel reports)
│   ├── helpers.py              # Shared utilities: get_fx_rate, quarter_months, clean_json, etc.
│   ├── commission_plans/
│   │   ├── __init__.py         # get_plan(role) registry
│   │   ├── base.py             # BaseCommissionPlan ABC
│   │   ├── sdr.py              # SDRCommissionPlan
│   │   └── cs.py               # CSACommissionPlan (Climate Strategy Advisors)
│   └── dashboards/
│       ├── base.py             # Shared HTML/CSS/JS (assemble_html, shared tab loaders)
│       │                       #   loadWorkings() — role-aware: CS branch vs SDR/AE/AM branch
│       │                       #   loadAccrualSummary() — employer-contrib detection by explicit
│       │                       #     type name, not by type !== 'Commission'
│       ├── sdr.py              # SDR-specific nav links, tab HTML, role JS
│       ├── cs.py               # CS-specific nav links, tab HTML, role JS
│       ├── ae.py               # AE-specific nav links, tab HTML, role JS
│       ├── am.py               # AM-specific nav links, tab HTML, role JS
│       └── __init__.py         # build_dashboard_html(role) dispatcher
│
├── data/                       # Input CSVs — gitignored (contains PII)
│   ├── README.txt              # Detailed data file spec (column names, formats, rules)
│   ├── humaans_export.csv      # Primary HR source (employees, salaries, managers)
│   ├── SAO_commission_data.csv # Salesforce CRM export (~4,830 rows)
│   ├── InputData.csv           # Closed-won ACV data (~2,122 rows)
│   ├── InvoiceSearchCommissions.csv  # NetSuite invoice matching (144 rows)
│   ├── employees.csv           # Fallback if humaans_export.csv absent
│   ├── fx_rates.csv            # EUR→SEK/GBP/USD monthly rates
│   ├── spif_targets.csv        # SPIF definitions
│   ├── approval_state.json     # Auto-managed approval state (safe to delete to reset)
│   │
│   │   # CS (Climate Strategy) performance inputs — filled by Finance each quarter
│   ├── cs_nrr.csv              # NRR% per employee per quarter
│   ├── cs_csat_sent.csv        # Total CSATs sent per employee per quarter (threshold check)
│   ├── cs_csat_scores.csv      # Individual CSAT scores 0–5 (one row per response)
│   ├── cs_credits.csv          # Service tier credits used % per employee per quarter
│   └── cs_referrals.csv        # CS referral SAOs and closed-won deals
│
├── output/statements/          # Generated PDFs (gitignored)
└── assets/normative_logo.png   # Used in PDF statements
```

---

## How the App Starts

```
python launch.py [--data-dir data] [--port 8050] [--no-browser]
```

1. Reads `config.ini` → extracts SMTP config into `SMTP_CONFIG` global
2. Calls `run_pipeline(data_dir)` → populates `MODEL` global (CommissionModel)
3. Loads `ApprovalState` from `data/approval_state.json` → `APPROVAL` global
4. Starts `HTTPServer` on `localhost:8050` (default)
5. Opens browser tab automatically (unless `--no-browser`)

**All data is loaded once at startup. No hot-reload, no background refresh.** Restart the process to pick up new CSV data.

---

## Global State (launch.py)

```python
MODEL: CommissionModel = None    # All DataFrames — populated by run_pipeline()
APPROVAL: ApprovalState = None   # JSON-backed approval states
SMTP_CONFIG: dict = {}           # From config.ini [smtp] section
DATA_DIR: str = "data"
```

Nothing is stored in a database or on disk beyond `approval_state.json`. The browser never stores commission data; it just fetches JSON from the API on demand.

---

## The 6-Stage Pipeline (src/pipeline.py)

`run_pipeline(data_dir)` runs sequentially at startup and returns a `CommissionModel`.

| Stage | What happens |
|---|---|
| 1 — Load | `load_all(data_dir)` reads all CSVs → populates employees, salary_history, sdr_activities, closed_won, fx_rates |
| 2 — Calendar | Discovers all months present in activity/closed_won data → `model.active_months` |
| 3 — Monthly | For each commissioned employee × each active month: calls `plan.calculate_monthly()` → appends to `monthly_rows` → `model.commission_monthly` DataFrame |
| 4 — Quarterly | For each employee × quarter: calls `plan.calculate_quarterly_accelerator()` → merges top-ups into commission_monthly at quarter-end month |
| 5 — Report table | Joins commission_monthly with employee metadata → `model.commission_detail` (the main reporting table used by all API endpoints) |
| 6 — SPIFs | `calculate_all_spifs()` → `model.spif_awards`; merges SPIF amounts into commission_monthly + rebuilds commission_detail |

**Pro-rata window**: employees are skipped for months before `plan_start_date` or after `plan_end_date` (from Humaans).

---

## CommissionModel (the in-memory data store)

```python
class CommissionModel:
    employees: pd.DataFrame        # employee_id, name, title, role, region,
                                   #   country, currency, manager_id, email,
                                   #   plan_start_date, plan_end_date
    salary_history: pd.DataFrame   # From Humaans; used for CS salary-based bonuses
    sdr_activities: pd.DataFrame   # Deduplicated SAOs from SAO_commission_data.csv
    closed_won: pd.DataFrame       # ACV rows from InputData.csv + InvoiceSearch, with
                                   #   is_forecast flag for unmatched deals
    fx_rates: pd.DataFrame         # month, EUR_SEK, EUR_GBP, EUR_USD
    commission_monthly: pd.DataFrame  # Employee × month commission rows
    accelerators: pd.DataFrame     # Quarterly accelerator rows before merge
    commission_detail: pd.DataFrame   # commission_monthly LEFT JOIN employees metadata
                                      # + quarter column — THE MAIN REPORTING TABLE
    spif_awards: pd.DataFrame      # SPIF award rows
    active_months: list[Timestamp] # Sorted list of all months with data
    default_month: Timestamp       # Last active month (default for UI)
    cs_performance: dict           # CS-specific inputs loaded from 5 CSVs:
                                   #   {"nrr": df, "csat_sent": df, "csat_scores": df,
                                   #    "credits": df, "referrals": df}
                                   # Empty DataFrames if files absent (graceful degradation)
```

**Total memory footprint: < 50 MB.** Largest raw input is SAO data (~4,830 rows, 744 KB on disk).

---

## Commission Plans (src/commission_plans/)

### Architecture

`BaseCommissionPlan` (ABC) defines the interface every plan must implement:

| Method | Purpose |
|---|---|
| `calculate_monthly(emp, month, activities, closed_won, fx_df, salary_history, cs_performance=None)` | Returns dict of commission components for one employee-month |
| `calculate_quarterly_accelerator(emp, year, quarter, activities, salary_history, cs_performance=None)` | Returns quarterly bonus/accelerator dict |
| `get_rates(currency)` | Returns rate schedule for the currency |
| `get_components()` | Returns ordered list of component keys (for UI columns) |

`cs_performance` is an optional dict of DataFrames (see CommissionModel above); SDR plans ignore it.

`get_plan(role)` in `__init__.py` is the registry — returns the plan class for a given role string, or `None` if not commissioned.

### SDR Plan

**Role**: `sdr` | **Payout frequency**: Monthly

**Rate tables** (fixed per-SAO amounts in local currency):

| Currency | Outbound SAO | Inbound SAO | Accelerator SAO |
|---|---|---|---|
| SEK | 1,300 | 590 | 2,000 |
| GBP | 100 | 47 | 155 |
| EUR | 115 | 55 | 175 |

**Closed-won commissions** (percentage of ACV in EUR, then FX'd to local):
- Outbound: 5% of ACV
- Inbound: 1% of ACV

**Quarterly accelerator**: Triggers when outbound SAOs in the quarter `>= 9`. Top-up = `excess_saos × (accelerator_rate - outbound_rate)`. Booked to the quarter-end month.

**Forecast vs actual**: `closed_won` rows have an `is_forecast` flag. Forecast commissions are calculated but only actual (invoiced) amounts count toward `total_commission`.

**Attainment %**: `(outbound_saos / 3) × 100` — monthly target = 3 outbound SAOs (display only, not a gate).

---

### CS Plan — Climate Strategy Advisors (src/commission_plans/cs.py)

**Role**: `cs` | **Payout frequency**: Quarterly (booked to Mar/Jun/Sep/Dec)

**Annual bonus**: 15% of base salary, prorated quarterly.
`quarterly_bonus_target = salary_monthly × 12 × 0.15 / 4`

Salary comes from `salary_history` (latest effective record at or before the quarter-end month).

**Three measures:**

| Measure | Weight | Source CSV | Target |
|---|---|---|---|
| NRR (Net Revenue Retention) | 50% | `cs_nrr.csv` | 100% NRR on individual book of business |
| CSAT | 35% | `cs_csat_sent.csv` + `cs_csat_scores.csv` | ≥90% avg score; ≥10 CSATs sent |
| Service tier credits usage | 15% | `cs_credits.csv` | 100% of credits used on renewals |

**NRR payout tiers** (50% weight):

| NRR achieved | Payout |
|---|---|
| < 90% | 0% |
| 90–91.99% | 50% |
| 92–93.99% | 60% |
| 94–95.99% | 70% |
| 96–97.99% | 80% |
| 98–99.99% | 90% |
| ≥ 100% | 100% |

**NRR accelerator**: For each 1% NRR above 100%, +2% of the NRR portion is added via `calculate_quarterly_accelerator()` and merged as `accelerator_topup`.

**CSAT payout tiers** (35% weight):
- Threshold: ≥10 CSATs sent in the quarter (from `cs_csat_sent.csv`), else 0%
- Scores: individual responses in `cs_csat_scores.csv` on a 0–5 scale → averaged → converted to 0–100%
- < 80%: 0% | 80–89.99%: 50% | ≥ 90%: 100%

**Service credits payout tiers** (15% weight):
- < 50%: 0% | 50–74.99%: 50% | 75–99.99%: 75% | 100%: 100%

**Referral commissions** (calculated monthly, same rates as SDR):
- Source: `data/cs_referrals.csv` — one row per referral, columns: `employee_id, date, account_name, referral_type, acv_eur, is_closed_won, is_forecast`
- Active referral (outbound): SEK 1,300 / GBP 100 / EUR 115 per SAO + 5% of ACV closed-won
- Inbound referral: SEK 590 / GBP 47 / EUR 55 per SAO + 1% of ACV closed-won
- 50/50 split when both CSA and AM named on a referral — managed in source data, not in code

**Accruals**: Finance accruals show `salary_monthly × 0.15` every month (full potential, regardless of actual performance) — not the actual payout. Actual bonus only appears in the quarter-end month row.

---

### Other Roles

AE, AM, SE — plans not yet implemented. `get_plan()` returns `None` for them, so they are skipped in Stage 3.

**Note on Customer Success**: Humaans titles matching "Customer Success" are mapped to role `customer_success` (no plan). The `cs` role code is reserved for **Climate Strategy** employees.

---

## Data Loading (src/loader.py)

### Employee data (two options)

**Option A — Humaans export** (`humaans_export.csv`): Preferred. `humaans_loader.py` parses it and auto-determines:
- Current role from latest role effective date
- Plan start date = first date they held the current commissioned role
- Salary history timeline for prorated bonuses
- Manager relationships via manager email → employee ID

**Job title → role mapping** (`_TITLE_RULES` in `humaans_loader.py`):

| Title pattern | Role |
|---|---|
| `Sales Development Representative *`, `Enterprise Sales Development Rep` | `sdr` |
| `Account Manager`, `Senior Account Manager` | `am` |
| `Account Executive`, `Mid-market AE` | `ae` |
| `Lead Climate Strategy Expert` | `cs` |
| `Senior Climate Strategy Advisor` | `cs` |
| `Associate Climate Strategy Advisor` | `cs` |
| `Climate Strategy Advisor` | `cs` |
| `Climate Strategy *` (catch-all) | `cs` |
| `Customer Success *` | `customer_success` (no plan) |
| `Solutions Engineer`, `Senior SE` | `se` |
| `VP Revenue`, `VP Sales`, `Head of Sales` | `sales_director` |
| `CFO`, `Chief Financial Officer` | `cfo` |
| Everything else | `other` (not commissioned) |

**Option B — employees.csv**: Manual fallback CSV. Same columns as what Humaans produces.

### SAO deduplication rules

From `SAO_commission_data.csv`:
- Rows where SDR column is blank → ignored
- Lead Source `"Outbound - *"` → `outbound`; `"Inbound - *"` → `inbound`; blank/unknown → ignored
- **6-month account deduplication**: if same Account Name already had a qualifying SAO in the past 6 months, second occurrence is excluded
- SDR name matched case-insensitively to employee name

### Closed-won routing

`InputData.csv` + `InvoiceSearchCommissions.csv` (NetSuite invoices) are joined. Rows matched to a NetSuite invoice → `is_forecast = False`. Unmatched pipeline deals → `is_forecast = True`.

---

## API Endpoints (launch.py)

All GET endpoints read from the `MODEL` global. All POST endpoints mutate `APPROVAL` state (write to disk) or trigger email sends.

### GET

| Endpoint | Description |
|---|---|
| `GET /` | Serves the entire SPA as a single HTML page |
| `GET /api/months` | List of active months |
| `GET /api/employees` | List of commissioned employees |
| `GET /api/team_overview?month=YYYY-MM-DD` | All employees for a month with KPIs |
| `GET /api/sdr_detail?employee_id=&month=` | One employee's commission breakdown |
| `GET /api/monthly_summary?month=` | Monthly totals per employee |
| `GET /api/quarterly_summary?year=&quarter=` | Quarterly rollup |
| `GET /api/commission_workings?employee_id=&month=` | Line-by-line workings (per SAO / per deal) |
| `GET /api/spifs` | All SPIF awards |
| `GET /api/approval_status?month=` | Approval state for all employees for a month |
| `GET /api/preview_pdf?employee_id=&month=` | Stream generated PDF |
| `GET /api/payroll_summary?year=` | Payroll summary for Finance |
| `GET /api/accrual_summary?year=` | Finance accruals summary |
| `GET /api/export_payroll?year=` | Download Payroll Excel workbook |
| `GET /api/export_accrual?year=` | Download Accruals Excel workbook |

### POST

| Endpoint | Description |
|---|---|
| `POST /api/approve` | `{employee_id, month}` → set status to `approved`, snapshot total |
| `POST /api/unapprove` | `{employee_id, month}` → revert to `pending` |
| `POST /api/send_approved` | `{month}` → generate PDF + email all approved-unsent employees |
| `POST /api/send_payroll` | `{year, email}` → email Payroll Excel to specified address |
| `POST /api/send_accrual` | `{year, email}` → email Accruals Excel to specified address |

---

## Approval State Machine (src/approval_state.py)

States per `(employee_id, month)` tuple: `pending` → `approved` → `sent`

- `approve(emp_id, month, total)` — snapshots the commission total at approval time
- `unapprove(emp_id, month)` — reverts to pending; clears snapshot
- `mark_sent(emp_id, month)` — marks as sent after email dispatch
- `check_and_reset_stale(emp_id, month, current_total)` — if the commission total changed since approval (new data loaded), auto-reverts to pending

State is persisted to `data/approval_state.json` on every write. Delete this file to reset all approvals.

---

## Email Flow (src/email_sender.py)

1. `_make_pdf(emp_id, month_str)` generates PDF to `output/statements/<emp_id>_<month>.pdf`
2. `send_statement(smtp_config, emp, month_label, total, currency, pdf_path, cc)` — SMTP send
3. CFO + Sales Director (`role=cfo`, `role=sales_director`) are auto-CC'd on all statements via `build_cc_list()`
4. `send_excel_report(smtp_config, to_email, subject, body, xlsx_bytes, filename)` — for payroll/accrual reports

SMTP config comes from `config.ini` `[smtp]` section. Required keys: `host`, `port`, `user`, `password`, `from_email`.

---

## Excel Exports (export_excel.py)

Two workbook types, both built with `openpyxl`:

- **Payroll Summary** (`export_payroll_workbook(model, year)`) — one sheet per month in the year, commission breakdown per employee, plus employer social contributions for UK and Nordic employees
- **Finance Accruals** (`export_accrual_workbook(model, year)`) — accrual view with local currency amounts and department codes; used by Finance for accounting entries

Both return raw `bytes` (in-memory workbook), suitable for HTTP response or email attachment.

---

## Frontend (src/dashboards/ + launch.py)

Single HTML page assembled at request time by `build_dashboard_html(role)`. No build step, no framework.

- **Chart.js** loaded from CDN for bar/line charts
- Each role has its own dashboard module (`src/dashboards/<role>.py`) that contributes: nav links, tab HTML panels, and role-specific JS. `base.py` provides the shared CSS, shared tab loaders, and `assemble_html()`.
- **JS loading order**: `role_js` is injected before `_SHARED_JS`. This means shared functions (e.g. `loadWorkings`) are defined last and win. Role-specific overrides must therefore live inside shared functions as role-detected branches (using `globalRole()`), not as top-level function redefinitions.
- **`loadWorkings()` is role-aware**: detects `globalRole() === 'cs'` and renders CS-specific KPI cards (Total Payout, NRR Bonus, CSAT Bonus, Credits Bonus, Referral Comm, Accelerator) and a 5-column table (Date · Component · Account/Period · Rate/Tier · Amount). SDR/AE/AM get the original 8-column SAO audit table.
- **`loadAccrualSummary()` banding**: employer-contribution rows are identified by explicit type name (`"Employer NI (13.8%)"`, `"Employer Social Contributions (31%)"`) — not by `type !== 'Commission'`. This ensures CS rows (`"CS Bonus Accrual (full potential)"`) are styled and totalled as commission, not as employer contributions.
- All data fetched via `fetch('/api/...')` calls to the local server
- PDF preview opens `/api/preview_pdf` in an iframe

---

## Key Business Rules to Know

1. **Commission currency is local** — SDRs and CSAs get paid in their local currency (SEK/GBP/EUR). ACV is in EUR and FX'd at the monthly rate from `fx_rates.csv`.

2. **Outbound vs inbound SAOs** — outbound pays ~2x inbound. Lead Source prefix in Salesforce determines type (SDR). For CS referrals the `referral_type` column in `cs_referrals.csv` determines type.

3. **Account deduplication (6 months)** — prevents double-paying SAO commissions for SDRs if the same account is worked twice within 6 months. Does not apply to CS referrals.

4. **SDR Accelerator is a top-up, not a replacement rate** — only the *excess* SAOs beyond the 9-threshold get the upgrade (delta between accelerator rate and standard outbound rate).

5. **CS bonus is quarterly, not monthly** — NRR/CSAT/credits bonus only appears in March/June/September/December rows. Non-quarter-end months show 0 unless referral commissions are present.

6. **CS accruals use full-potential salary basis** — Finance accruals show `salary_monthly × 0.15` every month regardless of actual NRR/CSAT/credits performance. Actual payout appears only at quarter-end.

7. **CS CSAT threshold** — if fewer than 10 CSATs are sent in a quarter (`cs_csat_sent.csv`), the entire CSAT measure pays 0 regardless of score. CSAT scores are 0–5 scale, averaged per employee per quarter, converted to 0–100%.

8. **CS NRR accelerator** — if NRR > 100%, an additional `(nrr_pct - 100) × 2% × NRR_portion` is booked as `accelerator_topup` via the quarterly accelerator pass.

9. **Forecast deals show in workings but don't pay** — deals in the pipeline not yet matched to a NetSuite invoice show in the commission workings view with a "Forecast" label but are excluded from `total_commission`.

10. **Stale approval auto-reset** — if commission figures change (e.g., a new CSV is loaded), any previously-approved month that has a different total is automatically reverted to pending to force re-review.

11. **Plan window enforcement** — if an employee joined mid-year or changed roles, `plan_start_date`/`plan_end_date` from Humaans ensure they only get commission for months they were in the role.

---

## Adding a New Commission Plan

1. Create `src/commission_plans/<role>.py` — subclass `BaseCommissionPlan`, implement all 4 abstract methods. See `cs.py` for a salary-based quarterly plan; `sdr.py` for a transaction-based monthly plan.
2. Register it in `src/commission_plans/__init__.py` `get_plan()` function.
3. Add the job title → role mapping(s) to `_TITLE_RULES` in `src/humaans_loader.py`.
4. The pipeline's Stage 3 will automatically pick it up for any employee whose `role` matches.
5. Update `payroll_summary()` and `accrual_summary()` in `src/reports.py` to include the new role. For `accrual_summary()`: the `type` string you assign to accrual rows must **not** be `"Employer NI (13.8%)"` or `"Employer Social Contributions (31%)"` — those are the only strings treated as employer contributions in the UI banding.
6. Update `_sheet_commission_workings()` in `export_excel.py` to include the new role.
7. Create `src/dashboards/<role>.py` — define `_NAV_LINKS`, `_TABS_HTML`, `_ROLE_JS`, and `build_html()`. Register it in `src/dashboards/__init__.py`. For role-specific workings rendering, add a branch inside `loadWorkings()` in `src/dashboards/base.py` (do not redefine `loadWorkings` in role JS — the shared JS loads last and would override it).
8. Update `generate_statement()` in `src/pdf_generator.py`: add a branch in the role dispatch to call new `_<role>_summary_page()` and `_<role>_workings_page()` functions.

---

## Common Debugging Starting Points

| Symptom | Where to look |
|---|---|
| Wrong SAO count | `loader.py` deduplication logic; check `SAO_commission_data.csv` Lead Source values |
| Wrong SDR commission total | `sdr.py` `calculate_monthly()` rate tables; `fx_rates.csv` for currency issues |
| SDR accelerator not triggering | `sdr.py` `calculate_quarterly_accelerator()` — threshold is `QUARTERLY_SAO_TARGET = 9` outbound |
| Employee missing from dashboard | `humaans_loader.py` `_TITLE_RULES` — check their job title mapping |
| CS employee missing | Check their Humaans title matches a "climate strategy" pattern in `_TITLE_RULES` |
| CS bonus showing 0 | Check `cs_nrr.csv`, `cs_csat_sent.csv`, `cs_credits.csv` have a row for (employee_id, year, quarter); verify `employee_id` matches exactly |
| CS CSAT bonus showing 0 | Verify `cs_csat_sent.csv` has `csats_sent >= 10` for the quarter; check `cs_csat_scores.csv` dates fall within the quarter |
| CS accrual not showing | `reports.py` `accrual_summary()` CS section; check `salary_history` has records for that employee |
| CS accrual rows dimmed/in wrong total | The `type` string for CS rows must not equal `"Employer NI (13.8%)"` or `"Employer Social Contributions (31%)"` — those are the only two strings `loadAccrualSummary()` treats as employer contributions |
| CS referral not appearing | Check `cs_referrals.csv` `employee_id` matches and `date` parses correctly; `is_closed_won` / `is_forecast` values |
| Approval auto-reset on refresh | `approval_state.py` `check_and_reset_stale()` — total changed since approval |
| Email not sending | `config.ini` SMTP section; check `launch.py` `SMTP_CONFIG` global |
| Forecast deal appearing in total | `closed_won_commission.py` invoice matching logic — should have `is_forecast=True` |
