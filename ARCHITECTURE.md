# Commission Calculator — Architecture & Codebase Reference

> Living document for onboarding future Claude sessions. Last updated: 2026-04-10. Changes: AE commission plan (10% base, 1% multi-year, annual accelerators, quarterly 50% gate, year-end true-up), SDR Lead commission plan (team SAO + ACV measures, £2,200/quarter), refactor of reports/pdf_generator/dashboards into sub-packages, CS referrals loaded from Salesforce DCT report (cs_referrals_report.csv), new data files (ae_targets.csv, sdr_lead_targets.csv, cs_*_report.csv).

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
+-- launch.py                   # Entry point: HTTP server + all API route handlers + embedded HTML
+-- export_excel.py             # Payroll and Finance Accruals Excel workbook builders
+-- config.ini                  # SMTP + runtime config (gitignored)
+-- requirements.txt
|
+-- src/
|   +-- pipeline.py             # 6-stage orchestration; defines CommissionModel dataclass
|   +-- loader.py               # CSV loading, SAO deduplication, data routing
|   +-- humaans_loader.py       # Humaans HR export parser; job title → role mapping
|   +-- closed_won_commission.py# ACV commission calculation from InputData + NetSuite invoices
|   |                           #   build_ae_closed_won_commission() — AE deal data from InputData
|   +-- cs_nrr_loader.py        # Computes NRR from cs_book_of_business.csv + InputData.csv
|   |                           #   compute_cs_nrr()          — per-CSA NRR (individual BoB)
|   |                           #   compute_cs_lead_nrr()     — team-aggregate NRR for cs_leads
|   |                           #   compute_cs_lead_multi_year_acv() — multi-year ACV deals
|   |                           #   NRR numerator = ARR + add_ons + one_off(50%) + upsell + churn
|   |                           #   one_off = 50% of Non-Recurring TCV on Add-On deals (CSA/AM split)
|   |                           #   Both NRR functions include synthetic churn for expired
|   |                           #   contracts (Renewal Date in YTD window, no renewal record)
|   |                           #   multi-year ACV: Opportunity Owner must be a CS employee
|   +-- spif.py                 # SPIF award calculation logic
|   +-- approval_state.py       # JSON-backed per-employee approval state machine
|   +-- email_sender.py         # SMTP email dispatch (statements + Excel reports)
|   +-- helpers.py              # Shared utilities: get_fx_rate, quarter_months, clean_json, etc.
|   +-- commission_plans/
|   |   +-- __init__.py         # get_plan(role) registry: sdr, cs, cs_lead, ae, sdr_lead
|   |   +-- base.py             # BaseCommissionPlan ABC
|   |   +-- sdr.py              # SDRCommissionPlan
|   |   +-- sdr_lead.py         # SDRLeadCommissionPlan (team SAO + ACV quarterly bonus)
|   |   +-- cs.py               # CSACommissionPlan (Climate Strategy Advisors)
|   |   +-- cs_lead.py          # CSLeadCommissionPlan (subclass of CSA; 20% bonus, team measures)
|   |   `-- ae.py               # AECommissionPlan (10% base + multi-year + annual accelerators)
|   +-- reports/
|   |   +-- __init__.py         # Re-exports all public report functions
|   |   +-- sdr.py              # team_overview, sdr_detail, monthly_summary, quarterly_summary
|   |   +-- cs.py               # cs_overview, cs_quarterly
|   |   +-- ae.py               # ae_overview, ae_detail, ae_monthly
|   |   `-- shared.py           # commission_workings, payroll_summary, accrual_summary,
|   |                           #   employee_list, available_months
|   +-- pdf/
|   |   +-- __init__.py         # Re-exports generate_statement
|   |   +-- generator.py        # generate_statement() — dispatches on employee["role"]
|   |   +-- _cover.py           # Cover page (logo, employee name, period, total)
|   |   +-- _sdr.py             # SDR summary + workings pages
|   |   +-- _cs.py              # CS summary + workings pages
|   |   +-- _ae.py              # AE summary + workings pages
|   |   +-- _constants.py       # Page margins, fonts, colours
|   |   `-- _helpers.py         # Shared drawing helpers
|   `-- dashboards/
|       +-- __init__.py         # build_dashboard_html(role) dispatcher
|       +-- base.py             # assemble_html(); imports from _styles, _shared_html, _shared_js
|       |                       #   loadWorkings() — role-aware: CS branch vs SDR/AE/AM branch
|       |                       #   loadAccrualSummary() — employer-contrib detection by explicit
|       |                       #     type name, not by type !== 'Commission'
|       +-- _styles.py          # Shared CSS (CSS constant)
|       +-- _shared_html.py     # SHARED_TABS_HTML, SHARED_MODALS constants
|       +-- _shared_js.py       # SHARED_JS constant (shared JS functions)
|       +-- sdr.py              # SDR-specific nav links, tab HTML, role JS
|       +-- cs.py               # CS-specific nav links, tab HTML, role JS
|       +-- ae.py               # AE-specific nav links, tab HTML, role JS
|       `-- am.py               # AM-specific nav links, tab HTML, role JS
|
+-- data/                       # Input CSVs — gitignored (contains PII)
|   +-- README.txt              # Detailed data file spec (column names, formats, rules)
|   +-- humaans_export.csv      # Primary HR source (employees, salaries, managers)
|   +-- SAO_commission_data.csv # Salesforce CRM export (~4,830 rows)
|   +-- InputData.csv           # Closed-won ACV data — SDR + AE deals; also NRR source
|   +-- InputData.xlsx          # Same source as InputData.csv (Excel format, optional)
|   +-- InvoiceSearchCommissions.csv  # NetSuite invoice matching (144 rows)
|   +-- employees.csv           # Fallback if humaans_export.csv absent
|   +-- fx_rates.csv            # EUR→SEK/GBP/USD monthly rates
|   +-- spif_targets.csv        # SPIF definitions
|   +-- ae_targets.csv          # AE quarterly + annual targets (employee_id, year, quarterly_target_eur,
|   |                           #   annual_target_eur, is_ramp_q1)
|   +-- sdr_lead_targets.csv    # SDR Lead quarterly targets (employee_id, year,
|   |                           #   sao_team_target_q, acv_team_target_eur_q, quarterly_bonus_gbp)
|   +-- approval_state.json     # Auto-managed approval state (safe to delete to reset)
|   |
|   |   # CS (Climate Strategy) performance inputs — filled by Finance each quarter
|   +-- cs_book_of_business.csv # Book of Business: one row per account per CSA
|   |                           #   col 6  (index 5)  = Account Name
|   |                           #   col 10 (index 9)  = Flat Renewal ACV (converted) — base ARR
|   |                           #   col 12 (index 11) = Account ID (15-char Salesforce ID)
|   |                           #   col 13 (index 12) = Renewal Date (DD/MM/YYYY)
|   |                           #   col 20 (index 19) = CSA 2026 — name matched to employees
|   +-- cs_csat_report.csv      # Salesforce CSAT-sent report (Subject, First Name, Last Name,
|   |                           #   Date, Assigned, Account Name); app computes csats_sent per
|   |                           #   employee per quarter automatically
|   +-- cs_csat_scores_report.csv # Salesforce CSAT-response report (CSA, Account,
|   |                           #   Survey Response: Created Date, Survey Response: Survey Response Name,
|   |                           #   Score); scores 1–5; app averages per employee per quarter
|   +-- cs_credits_report.csv   # Salesforce credit-ledger report (Credit Ledger Name,
|   |                           #   Contract Year Start/End Date, Credits Allocated,
|   |                           #   Credits Used in Contract Year, Account: CSA: Full Name)
|   `-- cs_referrals_report.csv # Salesforce DCT referral report (Company Referrer, DCT Discovery,
|                               #   Stage, Amount, Amount Currency, Lead Source); parsed by
|                               #   _parse_sf_referrals_report() in pipeline.py
|
+-- output/statements/          # Generated PDFs (gitignored)
`-- assets/normative_logo.png   # Used in PDF statements
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
    closed_won: pd.DataFrame       # ACV rows from InputData.csv + InvoiceSearch (SDR), with
                                   #   is_forecast flag for unmatched deals
    ae_closed_won: pd.DataFrame    # ACV rows for AE deals from InputData.csv + InvoiceSearch
    fx_rates: pd.DataFrame         # month, EUR_SEK, EUR_GBP, EUR_USD
    commission_monthly: pd.DataFrame  # Employee × month commission rows
    accelerators: pd.DataFrame     # Quarterly accelerator rows before merge
    commission_detail: pd.DataFrame   # commission_monthly LEFT JOIN employees metadata
                                      # + quarter column — THE MAIN REPORTING TABLE
    spif_awards: pd.DataFrame      # SPIF award rows
    active_months: list[Timestamp] # Sorted list of all months with data
    default_month: Timestamp       # Last active month (default for UI)
    cs_performance: dict           # Shared performance dict passed to all commission plans:
                                   #   CS keys:       "nrr", "nrr_breakdown", "nrr_targets",
                                   #                  "csat_sent", "csat_scores",
                                   #                  "credits", "credits_detail",
                                   #                  "referrals", "cs_lead_multi_year_acv"
                                   #   AE keys:       "ae_closed_won", "ae_targets"
                                   #   SDR Lead keys: "sdr_closed_won", "sdr_lead_targets"
                                   #   Shared:        "fx_rates"
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

`get_plan(role)` in `__init__.py` is the registry — returns the plan class for a given role string, or `None` if not commissioned. Registered roles: `sdr`, `cs`, `cs_lead`, `ae`, `sdr_lead`.

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

**Roles**: `cs` (CSA) and `cs_lead` (Team Lead) | **Payout frequency**: Quarterly (booked to Mar/Jun/Sep/Dec)

**Annual bonus**:
- CSA (`cs`): **15%** of base salary, prorated quarterly. `quarterly_bonus_target = salary_monthly × 12 × 0.15 / 4`
- Team Lead (`cs_lead`): **20%** of base salary, prorated quarterly. `quarterly_bonus_target = salary_monthly × 12 × 0.20 / 4`

Salary comes from `salary_history` (latest effective record at or before the quarter-end month).

**Three measures:**

| Measure | Weight | Source (CSA) | Source (Team Lead) | Target |
|---|---|---|---|---|
| NRR | 50% | Individual BoB via `cs_nrr_loader.compute_cs_nrr()` | Team-aggregate BoB via `compute_cs_lead_nrr()` | 100% NRR |
| CSAT | 35% | Individual scores in `cs_csat_scores.csv` | Team-aggregate scores | ≥90% avg; ≥10 sent |
| Service credits | 15% | `cs_credits.csv` (per CSA) | Team-aggregate credits (pooled in pipeline) | 100% used |

**NRR data source**: NRR is computed automatically from `cs_book_of_business.csv` + `InputData.csv` by `cs_nrr_loader.py`. No manual `cs_nrr.csv` needed.

**NRR formula**: `NRR = (ARR + add_ons + one_off + upsell_downsell + churn) / ARR × 100`
- `add_ons` = Attainment New ACV on `Type=Add-On` deals (recurring expansion)
- `one_off` = **50% of Non-Recurring TCV** on `Type=Add-On` deals — represents the CSA's share of one-off services (e.g. implementations). The AM receives the other 50%. Visible in workings as "One-off svc (50%)".
- `upsell_downsell` = Attainment New ACV on `Type=Renewal` (Closed Won)
- `churn` = Attainment New ACV on `Type=Renewal` (Closed Lost) — already negative in Salesforce

**Synthetic churn**: accounts in the BoB whose Renewal Date (column 13) falls within the YTD window (Jan 1 – Q end) and have no matching `Type=Renewal` record in InputData are treated as churned (−ARR added to the NRR numerator).

**Team Lead NRR/CSAT/Credits**: pools all accounts belonging to the lead's direct reports plus the lead's own accounts. Pipeline computes `compute_cs_lead_nrr()` separately and merges result into `cs_performance["nrr"]` alongside individual CSA rows.

**Team Lead extras** (on own accounts only):
- Multi-year ACV commission: 1% of multi-year portion of renewal ACV (TCV − flat ACV, or flat ACV × (years − 1)) for renewal deals with contract duration > 12 months **where the Opportunity Owner is a CS employee**. Deals owned by AMs/AEs are excluded even if the account is in the lead's BoB.
- Referral commissions: same rates as SDR referrals

**NRR targets are per-employee and quarterly-prorated.** Each CSA has an annual NRR target stored in `cs_nrr_targets.csv` (e.g. 96%). The quarterly target is derived using a 1:1:1:2 weighting (Q1–Q3 each get 1 part, Q4 gets 2 parts of the allowed loss budget):

```
allowed_loss   = 100% − annual_target          (e.g. 4% for a 96% target)
Q1 target      = 100% − allowed_loss × 1/5     (e.g. 99.2%)
Q2 target      = 100% − allowed_loss × 2/5     (e.g. 98.4%)
Q3 target      = 100% − allowed_loss × 3/5     (e.g. 97.6%)
Q4 target      = annual_target                  (e.g. 96.0%)
```

NRR is still computed YTD (Jan 1 → quarter-end) by `cs_nrr_loader.py`. The quarterly target is only used for payout tier mapping. If no target is set (defaults to 100%), the tier step stays at 2% (original behaviour).

**NRR payout tiers** (50% weight) — thresholds are relative to the quarterly target:

| NRR vs quarterly target | Payout |
|---|---|
| ≥ quarterly target | 100% |
| ≥ target − 1 step | 90% |
| ≥ target − 2 steps | 80% |
| ≥ target − 3 steps | 70% |
| ≥ target − 4 steps | 60% |
| ≥ target − 5 steps | 50% |
| < target − 5 steps | 0% |

Where `step = annual_target × 2% × quarterly_weight` (e.g. Q1 step = 96% × 2% × 1/5 = 0.384%; Q4 step = 1.92%). Implemented in `CSACommissionPlan._nrr_payout_fraction()` and `_quarterly_nrr_target()` in `cs.py`; inherited by `CSLeadCommissionPlan`.

**NRR accelerator**: For each 1% NRR above the quarterly target, +2% of the NRR portion is added via `calculate_quarterly_accelerator()` and merged as `accelerator_topup`. Accelerator is Q4-only for CSAs; cs_lead runs it for all quarters.

**CSAT payout tiers** (35% weight):
- Threshold: ≥10 CSATs sent in the quarter (from `cs_csat_sent.csv`), else 0%
- Scores: individual responses in `cs_csat_scores.csv` on a 0–5 scale → averaged → converted to 0–100%
- < 80%: 0% | 80–89.99%: 50% | ≥ 90%: 100%

**Service credits payout tiers** (15% weight):
- < 50%: 0% | 50–74.99%: 50% | 75–99.99%: 75% | 100%: 100%
- Credit rows for **churned accounts** are automatically excluded: `_load_credits()` in `pipeline.py` cross-references InputData for accounts with a `Renewal Closed Lost` whose close date falls in the same year-quarter as the credit's Contract Year End Date. This prevents double-penalising a CSA via both NRR churn and unused credits.
- CSAs with no credit rows at all in the period get 100% payout by default (no credits at risk).

**Referral commissions** (calculated monthly, same rates as SDR):
- Source: `data/cs_referrals_report.csv` — Salesforce DCT report export, parsed by `_parse_sf_referrals_report()` in `pipeline.py`
  - Key columns: `Company Referrer` (CSA name), `DCT Discovery` (SAO date), `Stage`, `Amount`, `Amount Currency`, `Lead Source`
  - A row with a DCT Discovery date earns the SAO commission; `Stage == "Closed Won"` additionally earns the ACV commission
  - Lead Source `"Outbound - *"` → `outbound`; else → `inbound`
- Active referral (outbound): SEK 1,300 / GBP 100 / EUR 115 per SAO + 5% of ACV closed-won
- Inbound referral: SEK 590 / GBP 47 / EUR 55 per SAO + 1% of ACV closed-won
- 50/50 split when both CSA and AM named on a referral — managed in source data, not in code

**Accruals**: Finance accruals show `salary_monthly × 0.15` every month (full potential, regardless of actual performance) — not the actual payout. Actual bonus only appears in the quarter-end month row.

---

### AE Plan — Account Executives (src/commission_plans/ae.py)

**Role**: `ae` | **Payout frequency**: Year-end (Q4 true-up)

**Commission structure**:
- Base rate: **10%** of 1st-year ACV
- Multi-year bonus: **+1%** of ACV on year-2+ portion of multi-year renewals
- Annual Accelerator 1: **12%** on incremental ACV between 100–150% of annual target
- Annual Accelerator 2: **15%** on incremental ACV above 150% of annual target

**Quarterly gate**: if a quarter's 1st-year ACV < 50% of the quarterly target, that quarter's ACV is excluded from the year-end calculation. Accelerators apply to total annual ACV regardless of gate.

**Booking pattern**: `calculate_monthly()` records ACV pipeline data but returns zero commission. `calculate_quarterly_accelerator()` is only active for Q4 — it sums full-year qualifying ACV, applies gate + accelerators, and books the total as `accelerator_topup`.

**Data sources**:
- AE deal data: `ae_closed_won` DataFrame in `cs_performance` — built by `build_ae_closed_won_commission()` in `closed_won_commission.py` from `InputData.csv` + `InvoiceSearchCommissions.csv`
- Targets: `data/ae_targets.csv` — columns: `employee_id`, `year`, `quarterly_target_eur`, `annual_target_eur`, `is_ramp_q1`

---

### SDR Lead Plan (src/commission_plans/sdr_lead.py)

**Role**: `sdr_lead` | **Payout frequency**: Quarterly

**Annual bonus pot**: £8,800 → **£2,200/quarter**

**Two team-level measures**:

| Measure | Weight | Default target |
|---|---|---|
| Team SAO count | 35% → £770/quarter | 54 SAOs/quarter |
| Team closed-won ACV (EUR) | 65% → £1,430/quarter | €223,500/quarter |

**Tiered payout** (same tiers for both measures):

| Attainment | Payout |
|---|---|
| ≥ 100% | 100% of measure pot |
| 75–99.99% | 75% |
| 50–74.99% | 50% |
| < 50% | 0% |

**Data sources**: team SAOs from `model.sdr_activities` (all SDR employees aggregated). Team ACV from `sdr_closed_won` (= `model.closed_won`, actual invoices only). Targets from `data/sdr_lead_targets.csv` — columns: `employee_id`, `year`, `sao_team_target_q`, `acv_team_target_eur_q`, `quarterly_bonus_gbp`.

The SDR Lead earns nothing from individual deals; this is a team-level bonus only. Commission is in GBP; FX conversion applies if the employee is paid in another currency.

---

### Other Roles

AM, SE — plans not yet implemented. `get_plan()` returns `None` for them, so they are skipped in Stage 3.

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
| `SDR Lead`, `SDR Team Lead` | `sdr_lead` |
| `Account Manager`, `Senior Account Manager` | `am` |
| `Account Executive`, `Mid-market AE` | `ae` |
| `Lead Climate Strategy Expert` | `cs_lead` |
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
| `GET /api/ae_overview?year=&quarter=` | AE pipeline + attainment for a quarter |
| `GET /api/ae_detail?employee_id=&year=&quarter=` | One AE's quarterly commission detail |
| `GET /api/ae_monthly?employee_id=&month=` | One AE's monthly deal workings |
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

8. **CS NRR quarterly targets** — each quarter has its own NRR target derived from the employee's annual target in `cs_nrr_targets.csv` using a 1:1:1:2 split (Q1 = `100 - loss/5`, Q4 = annual target). NRR is still YTD; only the payout tier threshold shifts each quarter. Tier step = `annual_target × 2% × quarterly_weight`. **CS NRR accelerator** — if NRR exceeds the quarterly target, an additional `(attainment_over_target × 2%) × NRR_portion` is booked as `accelerator_topup` via the quarterly accelerator pass.

9. **Forecast deals show in workings but don't pay** — deals in the pipeline not yet matched to a NetSuite invoice show in the commission workings view with a "Forecast" label but are excluded from `total_commission`.

10. **Stale approval auto-reset** — if commission figures change (e.g., a new CSV is loaded), any previously-approved month that has a different total is automatically reverted to pending to force re-review.

11. **Plan window enforcement** — if an employee joined mid-year or changed roles, `plan_start_date`/`plan_end_date` from Humaans ensure they only get commission for months they were in the role.

12. **One-off services split 50/50** — for Add-On deals, the Non-Recurring TCV (implementations, one-off services) is split equally between the CSA and the AM. The CSA's 50% share is added to their NRR numerator. The `Attainment New ACV` (recurring expansion) is credited 100% to the CSA.

13. **Multi-year ACV requires CS ownership** — team leads only earn multi-year ACV commission on renewal deals where they (or a CS colleague) are the Opportunity Owner. If the deal is owned by an AM/AE, no multi-year ACV commission is generated for the CS lead even if the account is in their BoB.

14. **Churned account credits excluded** — when an account churns (Renewal Closed Lost) in a given quarter, its credit rows for that same quarter are excluded from the service credits calculation. Period-specific: a Q2 churn does not retroactively affect Q1 credits.

15. **AE commission is a year-end true-up** — no commission is paid in Q1–Q3. The full year's ACV is calculated in Q4, applying the quarterly 50% gate per-quarter (failing quarters' ACV is excluded). Annual accelerators (12% / 15%) apply to total annual ACV regardless of gate.

16. **SDR Lead is team-only** — the SDR Lead earns nothing from individual deals. Bonus is purely based on the whole SDR team's SAO count and closed-won ACV vs targets. Two weighted measures: 35% SAO count, 65% ACV, each with tiered payout (0/50/75/100%).

---

## Adding a New Commission Plan

1. Create `src/commission_plans/<role>.py` — subclass `BaseCommissionPlan`, implement all 4 abstract methods. See `cs.py` for a salary-based quarterly plan; `sdr.py` for a transaction-based monthly plan; `ae.py` for a year-end true-up plan.
2. Register it in `src/commission_plans/__init__.py` `PLAN_REGISTRY` dict.
3. Add the job title → role mapping(s) to `_TITLE_RULES` in `src/humaans_loader.py`.
4. The pipeline's Stage 3 will automatically pick it up for any employee whose `role` matches.
5. Update `payroll_summary()` and `accrual_summary()` in `src/reports/shared.py` to include the new role. For `accrual_summary()`: the `type` string you assign to accrual rows must **not** be `"Employer NI (13.8%)"` or `"Employer Social Contributions (31%)"` — those are the only strings treated as employer contributions in the UI banding.
6. Update `_sheet_commission_workings()` in `export_excel.py` to include the new role.
7. Create `src/dashboards/<role>.py` — define `_NAV_LINKS`, `_TABS_HTML`, `_ROLE_JS`, and `build_html()`. Register it in `src/dashboards/__init__.py`. For role-specific workings rendering, add a branch inside `loadWorkings()` in `src/dashboards/_shared_js.py` (do not redefine `loadWorkings` in role JS — the shared JS loads last and would override it).
8. Create `src/pdf/_<role>.py` and add a branch in `generate_statement()` in `src/pdf/generator.py` to call `_<role>_summary_page()` and `_<role>_workings_page()`.

---

## Common Debugging Starting Points

| Symptom | Where to look |
|---|---|
| Wrong SAO count | `loader.py` deduplication logic; check `SAO_commission_data.csv` Lead Source values |
| Wrong SDR commission total | `sdr.py` `calculate_monthly()` rate tables; `fx_rates.csv` for currency issues |
| SDR accelerator not triggering | `sdr.py` `calculate_quarterly_accelerator()` — threshold is `QUARTERLY_SAO_TARGET = 9` outbound |
| Employee missing from dashboard | `humaans_loader.py` `_TITLE_RULES` — check their job title mapping |
| CS employee missing | Check their Humaans title matches a "climate strategy" pattern in `_TITLE_RULES` |
| CS bonus showing 0 | Check `cs_nrr_targets.csv`, `cs_csat_report.csv`, `cs_credits_report.csv` have data for (employee, year, quarter); verify `employee_id` matches exactly; confirm quarterly NRR meets the prorated quarterly target |
| NRR one-off not appearing | Verify Add-On deal has non-zero `Non-Recurring TCV (converted)` in InputData and the account is in the CSA's BoB |
| Multi-year ACV unexpected | Check Opportunity Owner in InputData — must be a CS employee; AMs/AEs are excluded. See `compute_cs_lead_multi_year_acv()` |
| Credits score wrong / churned included | Check InputData for Renewal Closed Lost rows for that account in the same quarter; `_load_credits()` in pipeline.py logs excluded accounts |
| CS CSAT bonus showing 0 | Verify `cs_csat_report.csv` has rows for the quarter; check `cs_csat_scores_report.csv` dates fall within the quarter; confirm ≥10 CSATs sent |
| CS accrual not showing | `src/reports/shared.py` `accrual_summary()` CS section; check `salary_history` has records for that employee |
| CS accrual rows dimmed/in wrong total | The `type` string for CS rows must not equal `"Employer NI (13.8%)"` or `"Employer Social Contributions (31%)"` — those are the only two strings `loadAccrualSummary()` treats as employer contributions |
| CS referral not appearing | Check `cs_referrals_report.csv` has a `Company Referrer` name matching the employee; verify `DCT Discovery` date parses; check `Stage` for closed-won rows |
| AE commission not appearing | Check `ae_targets.csv` has a row for the employee + year; verify `InputData.csv` has closed-won deals for the AE; Q4 only — no commission before year-end |
| AE gate failing | Quarter's ACV must be ≥ 50% of `quarterly_target_eur`; check `ae_targets.csv` target values |
| SDR Lead bonus not appearing | Check `sdr_lead_targets.csv` has a row for the employee + year; verify `sdr_activities` and `closed_won` have SDR team data |
| Approval auto-reset on refresh | `approval_state.py` `check_and_reset_stale()` — total changed since approval |
| Email not sending | `config.ini` SMTP section; check `launch.py` `SMTP_CONFIG` global |
| Forecast deal appearing in total | `closed_won_commission.py` invoice matching logic — should have `is_forecast=True` |
