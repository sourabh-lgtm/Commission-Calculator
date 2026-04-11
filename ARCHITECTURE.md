# Commission Calculator — Architecture & Navigation Reference

> Living document. Last updated: 2026-04-11. See `COMMISSION_PLANS.md` for full rate tables, formulas, and payout tiers.

---

## What This App Does

Internal tool for **Normative** that calculates, reviews, approves, and distributes monthly sales commission statements. Ingests Salesforce CRM exports and Humaans HR data, runs a rules engine, and serves a single-page web dashboard where Finance can review, approve, and email PDF statements to each employee.

**Tech Stack**: Python 3.12 · stdlib `HTTPServer` (no Flask/FastAPI) · pandas/numpy · openpyxl · reportlab · Chart.js (CDN)

---

## Directory Layout

```
Commission Calculator/
+-- launch.py                    # Entry point: HTTP server + all API route handlers + embedded SPA HTML
+-- dev.py                       # Auto-reload dev launcher (restarts on file change)
+-- export_excel.py              # Payroll + Finance Accruals Excel workbook builders
+-- config.ini                   # SMTP + runtime config (gitignored)
+-- requirements.txt             # pandas, numpy, openpyxl, reportlab
|
+-- src/
|   +-- pipeline.py              # 6-stage orchestrator; defines CommissionModel dataclass
|   |                            #   run_pipeline(data_dir) -> CommissionModel
|   |                            #   _load_cs_performance() -> dict (all plan inputs)
|   |                            #   _parse_sf_referrals_report() -> DataFrame
|   |                            #   _load_credits() -> DataFrame (with churn exclusion logic)
|   +-- loader.py                # CSV loading, SAO deduplication, data routing
|   |                            #   load_all(data_dir) -> dict of DataFrames
|   |                            #   load_sao_commission_data() -> SAOs with 6-month dedup
|   |                            #   build_closed_won_commission() -> SDR closed-won
|   |                            #   build_ae_closed_won_commission() -> AE closed-won
|   +-- humaans_loader.py        # Humaans HR export parser; job title -> role mapping
|   |                            #   load_humaans(data_dir) -> (employees_df, salary_history_df)
|   |                            #   _TITLE_RULES — title pattern -> role string
|   +-- closed_won_commission.py # ACV commission rows from InputData.csv + NetSuite invoices
|   |                            #   build_closed_won_commission() -> SDR/AM closed-won DataFrame
|   |                            #   build_ae_closed_won_commission() -> AE closed-won DataFrame
|   +-- cs_nrr_loader.py         # NRR from cs_book_of_business.csv + InputData.csv
|   |                            #   compute_cs_nrr()                   — individual CSA NRR
|   |                            #   compute_cs_lead_nrr()              — team-aggregate NRR
|   |                            #   compute_cs_director_nrr()          — director aggregate
|   |                            #   compute_cs_lead_multi_year_acv()   — multi-year ACV bonus
|   |                            #   compute_cs_director_multi_year_acv()
|   |                            #   BoB col 19 (index 19) = "CSA 2026" column
|   +-- am_nrr_loader.py         # NRR from am_book_of_business.csv + InputData.csv
|   |                            #   compute_am_nrr()         — individual AM NRR
|   |                            #   compute_am_lead_nrr()    — team-aggregate NRR
|   |                            #   compute_am_multi_year_acv() — multi-year ACV for AMs
|   |                            #   BoB col 18 (index 18) = "Account Owner 2026" column
|   |                            #   One-off services = 20% of Non-Recurring TCV (vs 50% for CS)
|   +-- spif.py                  # SPIF award calculation (Q1 2026)
|   |                            #   calculate_sdr_spif()   — 8-week window between SAO and close
|   |                            #   calculate_ae_spif()    — first AE to hit Q1 target
|   |                            #   calculate_all_spifs()  — combines both
|   +-- approval_state.py        # JSON-backed approval state machine (pending->approved->sent)
|   +-- email_sender.py          # SMTP email dispatch (statements + Excel reports)
|   |                            #   send_statement() — PDF attachment via SMTP
|   |                            #   send_excel_report() — Excel attachment via SMTP
|   |                            #   build_cc_list() — manager + CFO + sales_director
|   +-- helpers.py               # Shared utilities
|   |                            #   get_fx_rate(fx_df, month, currency) -> float
|   |                            #   month_to_quarter(month) -> "Q1 FY26"
|   |                            #   quarter_end_month(month) -> Timestamp
|   |                            #   quarter_months(year, quarter) -> [Timestamp x3]
|   |                            #   clean_json(obj) — handles NaN/Timestamp for JSON
|   +-- salary_history.py        # Prorated salary calculations for bonus-based roles (AM, CS)
|   |                            #   get_prorated_monthly_salary(salary_history, emp_id, start, end)
|   |                            #   get_role_segments() — salary segments with overlap weights
|   |                            #   quarter_date_range(year, quarter) -> (start, end)
|   |
|   +-- commission_plans/
|   |   +-- __init__.py          # get_plan(role) registry -> plan class or None
|   |   |                        #   PLAN_REGISTRY = {sdr, cs, cs_lead, cs_director,
|   |   |                        #                    ae, sdr_lead, am, am_lead}
|   |   +-- base.py              # BaseCommissionPlan ABC
|   |   |                        #   calculate_monthly() — returns dict of components
|   |   |                        #   calculate_quarterly_accelerator() — returns accelerator dict
|   |   |                        #   get_rates(currency) — rate schedule
|   |   |                        #   get_components() — ordered column list for UI
|   |   +-- sdr.py               # SDRCommissionPlan (fixed SAO rates + ACV %)
|   |   +-- sdr_lead.py          # SDRLeadCommissionPlan (team SAO + ACV quarterly bonus)
|   |   +-- cs.py                # CSACommissionPlan (NRR 50% + CSAT 35% + Credits 15%)
|   |   +-- cs_lead.py           # CSLeadCommissionPlan (subclass of CSA; 20% bonus; team measures)
|   |   +-- ae.py                # AECommissionPlan (10% base + 1% multi-yr + annual accelerators)
|   |   +-- am.py                # AMCommissionPlan (20% salary; NRR 100%; multi-yr ACV; referrals)
|   |   |                        #   Subclass of CSACommissionPlan (reuses NRR tier logic)
|   |   `-- am_lead.py           # AMLeadCommissionPlan (team-aggregate NRR; else same as AM)
|   |                            #   Subclass of AMCommissionPlan
|   |
|   +-- reports/
|   |   +-- __init__.py          # Re-exports all report functions
|   |   +-- sdr.py               # team_overview, sdr_detail, monthly_summary, quarterly_summary
|   |   +-- cs.py                # cs_overview, cs_quarterly
|   |   +-- ae.py                # ae_overview, ae_detail, ae_monthly
|   |   `-- shared.py            # commission_workings, payroll_summary, accrual_summary,
|   |                            #   employee_list, available_months
|   |
|   +-- pdf/
|   |   +-- __init__.py          # Re-exports generate_statement()
|   |   +-- generator.py         # generate_statement() — dispatches on employee["role"]
|   |   +-- _cover.py            # Cover page (logo, employee name, period, total)
|   |   +-- _sdr.py              # SDR summary + workings pages
|   |   +-- _cs.py               # CS/AM summary + workings pages
|   |   +-- _ae.py               # AE summary + workings pages
|   |   +-- _constants.py        # Page margins, fonts, colours
|   |   `-- _helpers.py          # Shared drawing helpers
|   |
|   `-- dashboards/
|       +-- __init__.py          # build_dashboard_html(role) dispatcher
|       +-- base.py              # assemble_html() — loadWorkings() role-aware (cs vs sdr/ae/am)
|       |                        #   loadAccrualSummary() — employer-contrib detected by exact type
|       |                        #   name string, not by type != "Commission"
|       +-- _styles.py           # Shared CSS constant
|       +-- _shared_html.py      # SHARED_TABS_HTML, SHARED_MODALS constants
|       +-- _shared_js.py        # SHARED_JS constant (shared JS; loads LAST, wins over role JS)
|       +-- sdr.py               # SDR nav links, tab HTML, role JS
|       +-- cs.py                # CS nav links, tab HTML, role JS
|       +-- ae.py                # AE nav links, tab HTML, role JS
|       `-- am.py                # AM nav links, tab HTML, role JS
|
+-- data/                        # Input CSVs — gitignored (contains PII)
|   +-- README.txt               # Column-level spec for every data file
|   +-- humaans_export.csv       # Primary HR source (employees, salaries, managers)
|   +-- SAO_commission_data.csv  # Salesforce SAO export (~4,830 rows)
|   +-- InputData.csv            # Salesforce opps — closed-won ACV; also NRR source
|   +-- InputData.xlsx           # Same source as InputData.csv (alternative format)
|   +-- InvoiceSearchCommissions.csv  # NetSuite invoice matching (144 rows)
|   +-- employees.csv            # Fallback if humaans_export.csv absent
|   +-- fx_rates.csv             # EUR->SEK/GBP/USD monthly rates
|   +-- spif_targets.csv         # SPIF definitions
|   +-- ae_targets.csv           # AE per-employee quarterly + annual targets
|   +-- sdr_lead_targets.csv     # SDR Lead quarterly team targets
|   +-- cs_book_of_business.csv  # CS Book of Business (one row per account per CSA)
|   +-- cs_nrr_targets.csv       # Per-CSA annual NRR targets (e.g. 96%)
|   +-- cs_csat_report.csv       # Salesforce CSAT-sent export (surveys sent per account)
|   +-- cs_csat_scores_report.csv# Salesforce CSAT-response export (scores 1-5)
|   +-- cs_credits_report.csv    # Salesforce credit-ledger export
|   +-- cs_referrals_report.csv  # Salesforce DCT referral report (CS + AM referrals)
|   +-- am_book_of_business.csv  # AM Book of Business (one row per account per AM)
|   +-- am_nrr_targets.csv       # Per-AM annual NRR targets
|   `-- approval_state.json      # Auto-managed approval state (delete to reset all)
|
+-- output/statements/           # Generated PDFs (gitignored)
`-- assets/normative_logo.png    # Used in PDF statements
```

---

## How the App Starts

```
python launch.py [--data-dir data] [--port 8050] [--no-browser]
```

1. Reads `config.ini` -> extracts SMTP config into `SMTP_CONFIG` global
2. Calls `run_pipeline(data_dir)` -> populates `MODEL` global (CommissionModel)
3. Loads `ApprovalState` from `data/approval_state.json` -> `APPROVAL` global
4. Starts `HTTPServer` on `localhost:8050`
5. Opens browser automatically (unless `--no-browser`)

**All data is loaded once at startup. No hot-reload.** Restart the process to pick up new CSV data.

---

## Global State (launch.py)

```python
MODEL: CommissionModel = None    # All DataFrames — populated by run_pipeline()
APPROVAL: ApprovalState = None   # JSON-backed approval states
SMTP_CONFIG: dict = {}           # From config.ini [smtp] section
DATA_DIR: str = "data"
```

Nothing is stored in a database. The browser fetches JSON from the local API on demand.

---

## The 6-Stage Pipeline (src/pipeline.py)

`run_pipeline(data_dir)` runs sequentially at startup and returns a `CommissionModel`.

| Stage | What happens |
|---|---|
| 1 — Load | `load_all()` reads all CSVs; `_load_cs_performance()` computes NRR for CS + AM |
| 2 — Calendar | Discovers all months in activity/closed_won data -> `model.active_months` |
| 3 — Monthly | For each commissioned employee x active month: `plan.calculate_monthly()` -> `commission_monthly` |
| 4 — Quarterly | For each employee x quarter: `plan.calculate_quarterly_accelerator()` -> merges topups into `commission_monthly` at quarter-end month |
| 5 — Report table | Joins `commission_monthly` with employee metadata -> `commission_detail` (main reporting table) |
| 6 — SPIFs | `calculate_all_spifs()` -> `spif_awards`; merges SPIF amounts into `commission_monthly` + rebuilds `commission_detail` |

**Pro-rata window**: employees are skipped for months before `plan_start_date` or after `plan_end_date` (from Humaans).

**`_load_cs_performance()`** (pipeline.py) is the big loader that calls:
- `compute_cs_nrr()`, `compute_cs_lead_nrr()`, `compute_cs_director_nrr()` from `cs_nrr_loader.py`
- `compute_am_nrr()`, `compute_am_lead_nrr()`, `compute_am_multi_year_acv()` from `am_nrr_loader.py`
- `_load_csat_sent()`, `_load_csat_scores()`, `_load_credits()` from pipeline.py itself

---

## CommissionModel (in-memory data store)

```python
class CommissionModel:
    employees: pd.DataFrame        # employee_id, name, title, role, region,
                                   #   country, currency, manager_id, email,
                                   #   plan_start_date, plan_end_date
    salary_history: pd.DataFrame   # Humaans salary timeline (effective_date, end_date,
                                   #   salary_monthly, salary_currency, role_at_time,
                                   #   title_at_time) — used for CS/AM salary-based bonuses
    sdr_activities: pd.DataFrame   # Deduplicated SAOs from SAO_commission_data.csv
    closed_won: pd.DataFrame       # SDR/AM closed-won from InputData + InvoiceSearch;
                                   #   is_forecast=True for unmatched pipeline deals
    ae_closed_won: pd.DataFrame    # AE deals from InputData + InvoiceSearch
    fx_rates: pd.DataFrame         # month, EUR_SEK, EUR_GBP, EUR_USD
    commission_monthly: pd.DataFrame  # Employee x month commission rows (output of stages 3-4)
    accelerators: pd.DataFrame     # Quarterly accelerator rows (before merge)
    commission_detail: pd.DataFrame   # commission_monthly + employee metadata + quarter label
                                      # THE MAIN REPORTING TABLE used by all API endpoints
    spif_awards: pd.DataFrame      # SPIF award rows
    active_months: list[Timestamp] # Sorted list of all months with data
    default_month: Timestamp       # Last active month (default for UI)
    cs_performance: dict           # Shared dict of DataFrames passed to all plan.calculate_*:
                                   #   CS/CS Lead:  "nrr", "nrr_breakdown", "nrr_targets",
                                   #                "csat_sent", "csat_scores",
                                   #                "credits", "credits_detail",
                                   #                "referrals", "cs_lead_multi_year_acv",
                                   #                "cs_director_multi_year_acv"
                                   #   AM/AM Lead:  "am_nrr", "am_nrr_breakdown",
                                   #                "am_nrr_targets", "am_multi_year_acv"
                                   #   AE:          "ae_closed_won", "ae_targets"
                                   #   SDR Lead:    "sdr_closed_won", "sdr_lead_targets"
                                   #   Shared:      "fx_rates", "employees"
                                   # Empty DataFrames if optional files absent (graceful degradation)
```

---

## Employee Data Loading (src/humaans_loader.py + src/loader.py)

**Option A — Humaans export** (`humaans_export.csv`): Preferred. Auto-determines current role, plan start date, salary history, and manager relationships.

**Job title -> role mapping** (`_TITLE_RULES` in `humaans_loader.py`):

| Title pattern | Role | Commission? |
|---|---|---|
| `Sales Development Representative *`, `Enterprise Sales Development Rep` | `sdr` | Yes |
| `SDR Lead`, `SDR Team Lead` | `sdr_lead` | Yes |
| `Account Manager`, `Senior Account Manager` | `am` | Yes |
| `Account Executive`, `Mid-market AE` | `ae` | Yes |
| `Lead Climate Strategy Expert` | `cs_lead` | Yes |
| `Climate Strategy Director` (or similar) | `cs_director` | Yes (uses CSLeadCommissionPlan) |
| `Senior/Associate Climate Strategy Advisor`, `Climate Strategy Advisor` | `cs` | Yes |
| `Customer Success *` | `customer_success` | No |
| `Solutions Engineer`, `Senior SE` | `se` | No |
| `VP Revenue`, `VP Sales`, `Head of Sales` | `sales_director` | No — CC on emails |
| `CFO`, `Chief Financial Officer` | `cfo` | No — CC on emails |
| Everything else | `other` | No |

**Plan registry** (`commission_plans/__init__.py`):
```python
PLAN_REGISTRY = {
    "sdr":         SDRCommissionPlan,
    "cs":          CSACommissionPlan,
    "cs_lead":     CSLeadCommissionPlan,
    "cs_director": CSLeadCommissionPlan,  # same plan; pipeline aggregates all CSAs
    "ae":          AECommissionPlan,
    "sdr_lead":    SDRLeadCommissionPlan,
    "am":          AMCommissionPlan,
    "am_lead":     AMLeadCommissionPlan,
}
```

---

## API Endpoints (launch.py)

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
| `GET /api/cs_overview?month=` | CS team overview + performance metrics |
| `GET /api/cs_quarterly?year=&quarter=` | CS quarterly detail |
| `GET /api/ae_overview?year=&quarter=` | AE pipeline + attainment for a quarter |
| `GET /api/ae_detail?employee_id=&year=&quarter=` | One AE's quarterly commission detail |
| `GET /api/ae_monthly?employee_id=&month=` | One AE's monthly deal workings |
| `GET /api/spifs` | All SPIF awards |
| `GET /api/approval_status?month=` | Approval state for all employees for a month |
| `GET /api/preview_pdf?employee_id=&month=` | Generate and stream PDF statement |
| `GET /api/payroll_summary?year=` | Finance payroll summary |
| `GET /api/accrual_summary?year=` | Finance accruals summary |
| `GET /api/export_payroll?year=` | Download Payroll Excel workbook |
| `GET /api/export_accrual?year=` | Download Accruals Excel workbook |

### POST

| Endpoint | Body | Action |
|---|---|---|
| `POST /api/approve` | `{employee_id, month}` | Set status to `approved`, snapshot total |
| `POST /api/unapprove` | `{employee_id, month}` | Revert to `pending` |
| `POST /api/send_approved` | `{month}` | Generate PDF + email all approved-unsent employees |
| `POST /api/send_payroll` | `{year, email}` | Email Payroll Excel to specified address |
| `POST /api/send_accrual` | `{year, email}` | Email Accruals Excel to specified address |

---

## Supporting Modules

### Approval State (src/approval_state.py)

States per `(employee_id, month)`: `pending` -> `approved` -> `sent`

- `approve(emp_id, month, total)` — snapshots commission total at approval time
- `unapprove(emp_id, month)` — reverts to pending; clears snapshot
- `mark_sent(emp_id, month)` — marks as sent after email dispatch
- `check_and_reset_stale(emp_id, month, current_total)` — if total changed since approval, auto-reverts to pending

Persisted to `data/approval_state.json`. Delete file to reset all approvals.

### Email Flow (src/email_sender.py)

1. Generate PDF to `output/statements/<emp_id>_<month>.pdf` via `src/pdf/generator.py`
2. `send_statement()` sends via SMTP (Gmail)
3. CC list: Manager + all CFO + all Sales Directors via `build_cc_list()`
4. SMTP config from `config.ini` `[smtp]` section: `host`, `port`, `user`, `password`, `from_email`

### Excel Exports (export_excel.py)

- `export_payroll_workbook(model, year)` — one sheet per month, rows = employees, employer social contributions for UK/Nordic
- `export_accrual_workbook(model, year)` — Finance accounting view with local currency amounts
- Both return raw `bytes` suitable for HTTP response or email attachment

### PDF Generation (src/pdf/)

`generate_statement()` in `generator.py` dispatches on `employee["role"]`:
- `sdr` -> `_sdr.py` (SAO/ACV breakdown)
- `cs`, `cs_lead`, `cs_director`, `am`, `am_lead` -> `_cs.py` (NRR/CSAT/Credits KPIs)
- `ae` -> `_ae.py` (ACV attainment, gate, accelerators)
- All roles get cover page from `_cover.py`

### Frontend (src/dashboards/)

Single HTML page assembled by `build_dashboard_html(role)` in `dashboards/__init__.py`. No build step.

**Key behaviour**: `_shared_js.py` is loaded LAST, so shared functions (e.g. `loadWorkings()`) win over role-specific JS. Role-specific UI branches live **inside** shared functions keyed by `globalRole()` — do not redefine shared functions in role JS files.

`loadWorkings()` is role-aware: `cs`/`am`/`cs_lead`/`am_lead` get CS-style KPI cards + 5-column table; `sdr`/`ae` get the 8-column SAO audit table.

`loadAccrualSummary()` identifies employer-contribution rows by exact type name (`"Employer NI (13.8%)"`, `"Employer Social Contributions (31%)"`) — not by `type != "Commission"`.

---

## Adding a New Commission Plan

1. Create `src/commission_plans/<role>.py` — subclass `BaseCommissionPlan`, implement all 4 methods. Reference: `cs.py` (salary-based quarterly), `sdr.py` (transaction-based monthly), `ae.py` (year-end true-up).
2. Register in `src/commission_plans/__init__.py` `PLAN_REGISTRY`.
3. Add job title -> role mappings to `_TITLE_RULES` in `src/humaans_loader.py`.
4. Add NRR/performance loading in `_load_cs_performance()` in `src/pipeline.py` if needed.
5. Update `payroll_summary()` and `accrual_summary()` in `src/reports/shared.py`. The `type` string for accrual rows must NOT be `"Employer NI (13.8%)"` or `"Employer Social Contributions (31%)"`.
6. Update `_sheet_commission_workings()` in `export_excel.py`.
7. Create `src/dashboards/<role>.py` — define `_NAV_LINKS`, `_TABS_HTML`, `_ROLE_JS`, `build_html()`. Register in `src/dashboards/__init__.py`. Add role-specific workings branch inside `loadWorkings()` in `_shared_js.py`.
8. Create `src/pdf/_<role>.py`; add branch in `src/pdf/generator.py`.

---

## Bug-to-File Lookup

> For formula details (rates, thresholds, tier tables), see `COMMISSION_PLANS.md`.

| Symptom | Primary file(s) | Key function / thing to check |
|---|---|---|
| **Employee loading** | | |
| Employee missing from dashboard entirely | `src/humaans_loader.py` | `_TITLE_RULES` — does their job title match a commissioned role? |
| Employee has wrong role | `src/humaans_loader.py` | `_TITLE_RULES` pattern ordering; check Humaans title exactly |
| Plan dates wrong (employee getting commission before/after tenure) | `src/humaans_loader.py` | `load_humaans()` — plan_start_date logic (first date they held the role) |
| Salary wrong for CS/AM bonus | `src/humaans_loader.py` | salary_history parsing; check effective_date order |
| Manager CC on emails wrong | `src/humaans_loader.py` | `_resolve_manager()` — matches manager email to employee_id |
| **SAO / SDR data** | | |
| Wrong SAO count for SDR | `src/loader.py` | `load_sao_commission_data()` — 6-month account deduplication |
| SAO classified as wrong type (in/outbound) | `src/loader.py` | Lead Source prefix check in `load_sao_commission_data()` |
| SDR name not matching | `src/loader.py` | Name matching logic (case-insensitive; last-name fallback) |
| **SDR commission** | | |
| Wrong SDR commission total | `src/commission_plans/sdr.py` | `calculate_monthly()` — check rate tables and FX |
| SDR accelerator not triggering | `src/commission_plans/sdr.py` | `calculate_quarterly_accelerator()` — threshold is `QUARTERLY_SAO_TARGET = 9` outbound |
| SDR accelerator amount wrong | `src/commission_plans/sdr.py` | Top-up = excess SAOs x (accelerator_rate - outbound_rate) — not full replacement rate |
| SDR closed-won commission missing | `src/closed_won_commission.py` | `build_closed_won_commission()` — check InputData + InvoiceSearch join; is_forecast flag |
| **AE commission** | | |
| AE commission not appearing | `src/commission_plans/ae.py` | Q4-only true-up; check `ae_targets.csv` has row for employee + year |
| AE gate failing unexpectedly | `src/commission_plans/ae.py` | `calculate_quarterly_accelerator()` — gate = 50% of `quarterly_target_eur` |
| AE multi-year bonus wrong | `src/commission_plans/ae.py` | Multi-year ACV is year-2+ portion; check InputData contract duration fields |
| AE accelerator tier wrong | `src/commission_plans/ae.py` | Tiers: 12% at 100-150%, 15% above 150% of annual_target_eur |
| AE ramp Q1 not paying | `src/commission_plans/ae.py` | `is_ramp_q1=True` in ae_targets.csv; all 5 pipeline criteria must be met |
| AE closed-won amount wrong | `src/closed_won_commission.py` | `build_ae_closed_won_commission()` — check Opportunity Owner field mapping |
| **CS commission** | | |
| CS bonus showing 0 (all measures) | `src/commission_plans/cs.py` | Check cs_nrr_targets.csv, cs_csat_report.csv, cs_credits_report.csv have data for (employee, quarter) |
| CS NRR wrong | `src/cs_nrr_loader.py` | `compute_cs_nrr()` — NRR formula; check BoB col 19 for CSA name; verify account ID 15-char match |
| CS NRR one-off not appearing | `src/cs_nrr_loader.py` | Add-On deal must have non-zero `Non-Recurring TCV (converted)` in InputData; 50% goes to CSA |
| CS NRR synthetic churn wrong | `src/cs_nrr_loader.py` | Accounts with Renewal Date in YTD window + no Renewal record -> synthetic churn (-ARR) |
| CS NRR target/tier wrong | `src/commission_plans/cs.py` | `_quarterly_nrr_target()` and `_nrr_payout_fraction()` — derived from cs_nrr_targets.csv annual target |
| CS NRR accelerator not appearing | `src/commission_plans/cs.py` | `calculate_quarterly_accelerator()` — Q4-only for CSA; all quarters for cs_lead |
| CS CSAT bonus showing 0 | `src/commission_plans/cs.py` | Threshold: >=10 CSATs sent in quarter; check cs_csat_report.csv dates; check cs_csat_scores_report.csv |
| CS credits score wrong | `src/commission_plans/cs.py` | `_load_credits()` in pipeline.py — churned account credits excluded; check Contract Year End Date falls in quarter |
| CS credits churned account included | `src/pipeline.py` | `_load_credits()` — cross-references InputData for Renewal Closed Lost; period-specific exclusion |
| CS referral not appearing | `src/pipeline.py` | `_parse_sf_referrals_report()` — check Company Referrer name match; DCT Discovery date parse |
| CS multi-year ACV unexpected | `src/cs_nrr_loader.py` | `compute_cs_lead_multi_year_acv()` — Opportunity Owner must be a CS employee |
| CS employee has wrong BoB | `src/cs_nrr_loader.py` | BoB col 19 (index 19) = "CSA 2026"; 15-char account ID match to InputData 18-char IDs |
| **AM commission** | | |
| AM bonus showing 0 | `src/commission_plans/am.py` | Check am_nrr_targets.csv has row for employee + year; verify am_book_of_business.csv loaded |
| AM NRR wrong | `src/am_nrr_loader.py` | `compute_am_nrr()` — BoB col 18 (index 18) = "Account Owner 2026"; 20% one-off (not 50%) |
| AM NRR account missing from BoB | `src/am_nrr_loader.py` | Check am_book_of_business.csv col 18 for AM name; 15-char account ID match |
| AM NRR target/tier wrong | `src/commission_plans/am.py` | Uses same `_quarterly_nrr_target()` / `_nrr_payout_fraction()` as CSA (inherited from cs.py) |
| AM NRR accelerator not appearing | `src/commission_plans/am.py` | `calculate_quarterly_accelerator()` — Q4-only; reads from cs_performance["am_nrr"] |
| AM multi-year ACV wrong | `src/am_nrr_loader.py` | `compute_am_multi_year_acv()` — 1% of year-2+ ACV on renewal deals in AM's BoB |
| AM Lead NRR wrong | `src/am_nrr_loader.py` | `compute_am_lead_nrr()` — team-aggregate of all AM accounts; check am_lead employee mapping |
| AM referral not appearing | `src/pipeline.py` + `src/commission_plans/am.py` | Referrals sourced from cs_referrals_report.csv; paid at quarter-end months only |
| **SDR Lead commission** | | |
| SDR Lead bonus not appearing | `src/commission_plans/sdr_lead.py` | Check sdr_lead_targets.csv has row for employee + year |
| SDR Lead SAO count wrong | `src/commission_plans/sdr_lead.py` | Uses model.sdr_activities (all SDR team); check sdr activities loaded correctly |
| SDR Lead ACV amount wrong | `src/commission_plans/sdr_lead.py` | Uses cs_performance["sdr_closed_won"] — actual invoiced only (no forecast) |
| **Data loading** | | |
| Closed-won deal showing as forecast | `src/closed_won_commission.py` | Invoice matching in `build_closed_won_commission()` — check InvoiceSearchCommissions.csv |
| FX rate wrong / missing | `src/helpers.py` | `get_fx_rate()` — fallback behavior; check fx_rates.csv has the month |
| NRR double-counting multi-line deals | `src/cs_nrr_loader.py` / `src/am_nrr_loader.py` | Deduplicated by Opportunity Id Casesafe before aggregating |
| **UI / dashboard** | | |
| Workings table wrong columns or data | `src/dashboards/base.py` (_shared_js.py) | `loadWorkings()` — CS branch vs SDR/AE/AM branch; role detection via `globalRole()` |
| Accrual rows showing in wrong section | `src/dashboards/base.py` (_shared_js.py) | `loadAccrualSummary()` — employer rows MUST match exact strings "Employer NI (13.8%)" or "Employer Social Contributions (31%)" |
| Dashboard not loading for a role | `src/dashboards/__init__.py` | Check role is registered; check `build_html()` in role's dashboard module |
| **Approval / email** | | |
| Approval auto-reset on refresh | `src/approval_state.py` | `check_and_reset_stale()` — total changed since approval (new CSV data) |
| Email not sending | `launch.py` + `src/email_sender.py` | Check `SMTP_CONFIG` global; check `config.ini` [smtp] section |
| PDF generation failing | `src/pdf/generator.py` | Check role branch exists; check `assets/normative_logo.png` path |
| Wrong employees CC'd on email | `src/email_sender.py` | `build_cc_list()` — uses `role=cfo` and `role=sales_director` from employees |
| **Excel export** | | |
| Employee missing from payroll workbook | `export_excel.py` | `export_payroll_workbook()` — check role is included in the sheet logic |
| Accrual amounts wrong | `src/reports/shared.py` | `accrual_summary()` — CS uses `salary_monthly * 0.15` regardless of actual performance |
