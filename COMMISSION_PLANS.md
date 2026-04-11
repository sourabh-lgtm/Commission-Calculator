# Commission Plans — Rates, Formulas & Payout Tiers

> This file documents the math behind every commission plan. For which file to edit, see `ARCHITECTURE.md`.
> Last updated: 2026-04-11 (SE commission plan: dashboard, PDF, accruals, payroll; AM dashboard + PDF; OO product code filter for one-off services).

---

## Plan Registry

```python
# src/commission_plans/__init__.py
PLAN_REGISTRY = {
    "sdr":         SDRCommissionPlan,          # src/commission_plans/sdr.py
    "cs":          CSACommissionPlan,          # src/commission_plans/cs.py
    "cs_lead":     CSLeadCommissionPlan,       # src/commission_plans/cs_lead.py
    "cs_director": CSLeadCommissionPlan,       # same plan as cs_lead; pipeline aggregates all CSAs
    "ae":          AECommissionPlan,           # src/commission_plans/ae.py
    "sdr_lead":    SDRLeadCommissionPlan,      # src/commission_plans/sdr_lead.py
    "am":          AMCommissionPlan,           # src/commission_plans/am.py
    "am_lead":     AMLeadCommissionPlan,       # src/commission_plans/am_lead.py
}
```

`get_plan(role)` returns the class or `None` (not commissioned). Stage 3 of the pipeline calls `plan.calculate_monthly()` for every employee whose role is in the registry.

---

## BaseCommissionPlan Interface (src/commission_plans/base.py)

Every plan implements:

```python
def calculate_monthly(emp, month, activities, closed_won, fx_df, salary_history, cs_performance=None) -> dict
    # Returns dict of commission components for one employee-month.
    # Non-quarter-end months: salary-based plans return 0 bonus, just pipeline data.

def calculate_quarterly_accelerator(emp, year, quarter, activities, salary_history, cs_performance=None) -> dict
    # Returns quarterly bonus / accelerator top-up dict.
    # Merged into commission_monthly at the quarter-end month row by the pipeline.

def get_rates(currency) -> dict
    # Returns rate schedule for the currency (used by UI for display).

def get_components() -> list[str]
    # Returns ordered list of component keys (determines UI column order).

def get_workings_rows(emp, month, activities, closed_won, fx_df, cs_performance=None) -> list[dict]
    # Returns per-deal / per-SAO rows for the commission workings detail view.
```

`cs_performance` is the dict of DataFrames from `CommissionModel.cs_performance`. SDR plans ignore it.

---

## SDR Plan (src/commission_plans/sdr.py)

**Payout frequency**: Monthly  
**Role**: `sdr`

### SAO Rate Table (fixed per-SAO, local currency)

| Currency | Outbound SAO | Inbound SAO | Accelerator SAO |
|---|---|---|---|
| SEK | 1,300 | 590 | 2,000 |
| GBP | 100 | 47 | 155 |
| EUR | 115 | 55 | 175 |

### Closed-Won ACV Commission (% of EUR ACV, FX'd to local)

| Type | Rate |
|---|---|
| Outbound closed-won | 5% of ACV |
| Inbound closed-won | 1% of ACV |

`is_forecast=True` rows: shown in workings but **excluded** from `total_commission`.

### Quarterly Accelerator

- Trigger: outbound SAOs in the quarter **>= 9** (`QUARTERLY_SAO_TARGET = 9`)
- Top-up = `excess_saos × (accelerator_rate − outbound_rate)` — delta only, not replacement
- Booked to the **quarter-end month** row via `calculate_quarterly_accelerator()`

### Attainment Display

`(outbound_saos / 3) × 100` — monthly target = 3 SAOs for display only (not a gate; no commission withheld if below target).

### Data Sources

- SAOs: `model.sdr_activities` (from `SAO_commission_data.csv` after 6-month account deduplication)
- Closed-won: `model.closed_won` filtered to SDR employee (from `InputData.csv` + `InvoiceSearchCommissions.csv`)
- FX rates: `model.fx_rates`

---

## CS Plan — Climate Strategy Advisors (src/commission_plans/cs.py)

**Payout frequency**: Quarterly (booked to Mar / Jun / Sep / Dec)  
**Roles**: `cs` (CSA), `cs_lead` (Team Lead), `cs_director`

### Annual Bonus Base

| Role | Annual Bonus % | Quarterly Target Formula |
|---|---|---|
| `cs` (CSA) | 15% | `salary_monthly × 12 × 0.15 / 4` |
| `cs_lead` | 20% | `salary_monthly × 12 × 0.20 / 4` |
| `cs_director` | 20% | same as cs_lead |

Salary comes from `salary_history` — prorated by calendar days if salary changed mid-quarter.

### Three Measures

| Measure | Weight | CSA Source | CS Lead Source |
|---|---|---|---|
| NRR | 50% | Individual BoB via `compute_cs_nrr()` | Team-aggregate via `compute_cs_lead_nrr()` |
| CSAT | 35% | Individual scores in `cs_csat_scores_report.csv` | Team-aggregate scores |
| Service Credits | 15% | `cs_credits_report.csv` per CSA | Team-aggregate credits |

### NRR Computation (src/cs_nrr_loader.py)

**Formula** (YTD from Jan 1 to quarter-end):
```
NRR = (ARR + add_ons + one_off + upsell_downsell + churn) / ARR × 100
```

| Component | Source | Notes |
|---|---|---|
| `ARR` | `cs_book_of_business.csv` col 10 (index 9) = "Flat Renewal ACV (converted)" | Base denominator |
| `add_ons` | InputData `Attainment New ACV` where `Type=Add-On` | Recurring expansion |
| `one_off` | **50%** of `Price × Quantity` for lines where `Product Code` starts with `"OO"` and `Type=Add-On` | Summed pre-dedup per opportunity; OO total merged onto deduplicated table |
| `upsell_downsell` | InputData `Attainment New ACV` where `Type=Renewal` + not Closed Lost | Renewal delta |
| `churn` | InputData `Attainment New ACV` where `Type=Renewal` + `Stage=Closed Lost` | Already negative |

**Synthetic churn**: Accounts in BoB with `Renewal Date` (col 13) in the YTD window but **no matching Renewal record** in InputData → treated as churned (−ARR added to numerator).

**Account ID matching**: BoB uses 15-char Salesforce IDs; InputData uses 18-char. Matched on first 15 chars.

**BoB column indices** (cs_book_of_business.csv):
- Index 5 = Account Name
- Index 9 = Flat Renewal ACV (converted)
- Index 11 = Account ID
- Index 12 = Renewal Date (DD/MM/YYYY)
- Index 19 = CSA 2026 (employee name)

### NRR Targets (cs_nrr_targets.csv)

Each CSA has an annual NRR target (e.g. 96%). Quarterly target derived by 1:1:1:2 split of the allowed-loss budget:

```
allowed_loss = 100% − annual_target      (e.g. 4% for 96% target)
Q1 target    = 100% − allowed_loss × 1/5  (e.g. 99.2%)
Q2 target    = 100% − allowed_loss × 2/5  (e.g. 98.4%)
Q3 target    = 100% − allowed_loss × 3/5  (e.g. 97.6%)
Q4 target    = annual_target              (e.g. 96.0%)
```

NRR is still computed YTD by `cs_nrr_loader.py`. The quarterly target is only used for payout tier mapping.

**Tier step** = `annual_target × 2% × quarterly_weight`  
(e.g. Q1: `96% × 2% × 1/5 = 0.384%`; Q4: `96% × 2% × 2/5 = 0.768%` … wait, Q4 weight = 2/5 of the 5-part budget = 2 parts)

Implemented in `_quarterly_nrr_target()` and `_nrr_payout_fraction()` in `cs.py`.

### NRR Payout Tiers (50% weight)

| NRR vs quarterly target | Payout fraction |
|---|---|
| >= quarterly target | 100% |
| >= target − 1 step | 90% |
| >= target − 2 steps | 80% |
| >= target − 3 steps | 70% |
| >= target − 4 steps | 60% |
| >= target − 5 steps | 50% |
| < target − 5 steps | 0% |

Default target = 100% if no entry in cs_nrr_targets.csv; step = 2% (original behaviour).

### NRR Accelerator

- For each 1% NRR above the quarterly target: `+2%` of the NRR portion added as `accelerator_topup`
- Formula: `(nrr_pct / q_nrr_target × 100 − 100) × 0.02 × (quarterly_bonus_target × 0.50)`
- **CSA**: Q4 only
- **CS Lead / CS Director**: all quarters

### CSAT Payout Tiers (35% weight)

- **Threshold**: >= 10 CSATs sent in the quarter (from `cs_csat_report.csv`); else entire CSAT measure = 0%
- **Scores**: 0–5 scale from `cs_csat_scores_report.csv` → averaged → converted to 0–100%

| CSAT average (0–100%) | Payout fraction |
|---|---|
| >= 90% | 100% |
| 80–89.99% | 50% |
| < 80% | 0% |

### Service Credits Payout Tiers (15% weight)

- `credits_used_pct = Credits Used in Contract Year / Credits Allocated × 100`
- Contract Year End Date must fall within the commission quarter
- Churned accounts (Renewal Closed Lost in same quarter) excluded — see `_load_credits()` in `pipeline.py`
- CSAs with no credit rows in the period: default 100% payout

| Credits used % | Payout fraction |
|---|---|
| 100% | 100% |
| 75–99.99% | 75% |
| 50–74.99% | 50% |
| < 50% | 0% |

### Referral Commissions (CS)

Source: `data/cs_referrals_report.csv` (Salesforce DCT export), parsed by `_parse_sf_referrals_report()` in `pipeline.py`.

Key columns: `Company Referrer` (CSA name), `DCT Discovery` (SAO date), `Stage`, `Amount`, `Amount Currency`, `Lead Source`.

| Referral type | SAO commission | Closed-won ACV commission |
|---|---|---|
| Outbound | SEK 1,300 / GBP 100 / EUR 115 | 5% of ACV |
| Inbound | SEK 590 / GBP 47 / EUR 55 | 1% of ACV |

50/50 split when both CSA and AM named — managed in source data, not in code.

### CS Lead / CS Director Extras

- **Team measures**: NRR/CSAT/Credits pooled from lead's own accounts + all direct reports' accounts
- **Multi-year ACV commission**: 1% of year-2+ ACV on renewal deals where `Opportunity Owner` is a CS employee. Deals owned by AM/AE are excluded even if account is in the lead's BoB.
  - Computed by `compute_cs_lead_multi_year_acv()` / `compute_cs_director_multi_year_acv()` in `cs_nrr_loader.py`
  - Booked at the deal's close-date month via `calculate_monthly()`
- **NRR accelerator**: runs for ALL quarters (not just Q4 like CSA)

### Accruals

Finance accruals show `salary_monthly × 0.15` every month (full potential) regardless of actual NRR/CSAT/Credits. Actual bonus only appears in the quarter-end month row.

---

## AE Plan — Account Executives (src/commission_plans/ae.py)

**Payout frequency**: Year-end (Q4 true-up only)  
**Role**: `ae`

### Commission Structure

| Component | Rate | Applies to |
|---|---|---|
| Base rate | 10% | 1st-year ACV of every deal |
| Multi-year bonus | +1% | Year-2+ ACV on multi-year renewal deals |
| Accelerator 1 | 12% | Incremental ACV between 100–150% of annual target |
| Accelerator 2 | 15% | Incremental ACV above 150% of annual target |

Accelerators apply to **total annual ACV** regardless of quarterly gate status.

### Quarterly Gate

- If a quarter's 1st-year ACV < **50%** of `quarterly_target_eur`, that quarter's ACV is **excluded** from the year-end calculation.
- Gate does not affect accelerator calculation.

### Booking Pattern

- `calculate_monthly()`: records ACV pipeline data but returns **zero commission amounts**.
- `calculate_quarterly_accelerator()` is **active only in Q4**:
  1. Sums all qualifying quarters' ACV (gate applied per quarter)
  2. Applies 10% base + 1% multi-year
  3. Applies accelerator tiers (12% / 15%) on total annual ACV
  4. Books total as `accelerator_topup` to the Q4 (December) month row

### AE Ramp Plan (Q1 only)

When `is_ramp_q1=True` in `ae_targets.csv`, if the AE meets **all 5 pipeline criteria** they receive 50% of quarterly OTE (`quarterly_target_eur × BASE_RATE`) as a Q1 bonus instead of the standard gate mechanism.

5 criteria (from `ae_ramp_report.csv`):
1. Pipeline Value >= €200,000
2. Customers at Solutions Design+ stage >= 7
3. Multi-threaded opportunities >= Solutions Design stage opportunities
4. Self-generated pipeline >= 50% of total
5. (implicit: active solutions design deals present)

### Data Sources

| Source | File | Key columns |
|---|---|---|
| AE deal data | `data/ae_targets.csv` | `employee_id`, `year`, `quarterly_target_eur`, `annual_target_eur`, `is_ramp_q1` |
| AE closed-won | `cs_performance["ae_closed_won"]` | Built by `build_ae_closed_won_commission()` from InputData + InvoiceSearch |
| Ramp criteria | `data/ae_ramp_report.csv` | Pipeline criteria per AE per quarter |

---

## SDR Lead Plan (src/commission_plans/sdr_lead.py)

**Payout frequency**: Quarterly  
**Role**: `sdr_lead`

### Annual Bonus Structure

Annual pot: **£8,800** → **£2,200/quarter**

| Measure | Weight | Pot/quarter | Default target |
|---|---|---|---|
| Team SAO count | 35% | £770 | 54 SAOs/quarter |
| Team closed-won ACV (EUR) | 65% | £1,430 | €223,500/quarter |

Both measures use the same tiered payout:

| Attainment | Payout |
|---|---|
| >= 100% | 100% of measure pot |
| 75–99.99% | 75% |
| 50–74.99% | 50% |
| < 50% | 0% |

The SDR Lead earns **nothing** from individual deals — team-level bonus only. FX applies if paid in non-GBP currency.

### Data Sources

| Source | Key |
|---|---|
| Team SAOs | `model.sdr_activities` (all SDR employees aggregated) |
| Team ACV | `cs_performance["sdr_closed_won"]` (actual invoiced only, no forecast) |
| Targets | `data/sdr_lead_targets.csv` — `employee_id`, `year`, `sao_team_target_q`, `acv_team_target_eur_q`, `quarterly_bonus_gbp` |

---

## AM Plan — Account Managers (src/commission_plans/am.py)

**Payout frequency**: Quarterly  
**Role**: `am`  
**Inherits from**: `CSACommissionPlan` (reuses NRR tier logic)

### Annual Bonus Base

| Role | Annual Bonus % | Quarterly Target Formula |
|---|---|---|
| `am` | 20% | `salary_monthly × 12 × 0.20 / 4` |
| `am_lead` | 20% | same |

### Measure: NRR — 100% Weight

Single measure. No CSAT, no Service Credits.

NRR tier structure is **identical** to CSA plan (same `_quarterly_nrr_target()` and `_nrr_payout_fraction()` methods inherited from `cs.py`).

Targets from `am_nrr_targets.csv` (columns: `employee_id`, `year`, `nrr_target_pct`).

### NRR Computation (src/am_nrr_loader.py)

**Formula**: identical to CS NRR formula.

```
NRR = (ARR + add_ons + one_off + upsell_downsell + churn) / ARR × 100
```

**Key difference from CS**: none for one-off services — both CS and AM identify one-off services by `Product Code` starting with `"OO"` and apply **50%** of `Price × Quantity` per OO line.

**BoB column indices** (am_book_of_business.csv):
- Index 5 = Account Name
- Index 9 = Flat Renewal ACV (converted)
- Index 11 = Account ID (15-char Salesforce ID)
- Index 12 = Renewal Date (DD/MM/YYYY)
- Index 18 = Account Owner 2026 (AM name)

### NRR Accelerator

- For each 1% NRR above quarterly target: `+2%` of NRR portion added as `accelerator_topup`
- **Q4 only** (same as CSA)
- Computed in `calculate_quarterly_accelerator()` — reads from `cs_performance["am_nrr"]`

### Multi-Year ACV Commission

- Rate: **1%** of year-2+ ACV on renewal deals in the AM's BoB
- Booked at the deal's close-date month via `calculate_monthly()`
- Source: `cs_performance["am_multi_year_acv"]` — computed by `compute_am_multi_year_acv()` in `am_nrr_loader.py`
- No break-clause adjustment in data; apply manually via SPIF if needed

### Referral Commissions

Same rates as CSA referrals (sourced from `cs_referrals_report.csv`):
- Outbound: SEK 1,300 / GBP 100 / EUR 115 per SAO + 5% ACV
- Inbound: SEK 590 / GBP 47 / EUR 55 per SAO + 1% ACV
- Paid at quarter-end months only

---

## AM Lead Plan (src/commission_plans/am_lead.py)

**Role**: `am_lead`  
**Inherits from**: `AMCommissionPlan`

Structurally identical to AM, with one difference:

- **NRR is team-aggregate** (all AM accounts pooled) computed by `compute_am_lead_nrr()` in `am_nrr_loader.py`
- Workings label shows "Team NRR" instead of "NRR"
- Multi-year ACV and referrals: same as individual AM, based on lead's own BoB only

---

## SE Plan — Solutions Engineers (src/commission_plans/se.py)

**Payout frequency**: Quarterly (booked to Mar / Jun / Sep / Dec)  
**Role**: `se`  
**Employees**: Kathleen Howard (Sweden/SEK), Polly (UK/GBP)

### Annual Bonus Base

| Role | Annual Bonus % | Quarterly Target Formula |
|---|---|---|
| `se` | 20% | `salary_monthly × 12 × 0.20 / 4` |

Salary comes from `salary_history` — prorated if salary changes mid-quarter.

### Two Measures

| Measure | Weight | Description |
|---|---|---|
| Global New Business ACV | 80% | Company-wide new business closed in the quarter vs quarterly target |
| Company Closing ARR | 20% | Company total ARR at quarter end vs quarterly target |

### Quarterly Targets (fixed in contract)

| Quarter | New Business Target (EUR) | ARR Target (EUR) |
|---------|--------------------------|------------------|
| Q1 | €568,000 | €11,116,000 |
| Q2 | €590,000 | €11,825,000 |
| Q3 | €641,000 | €12,464,000 |
| Q4 | €748,000 | €13,240,000 |

### Payout Tiers (identical for both measures)

| Achievement | Payout fraction |
|---|---|
| >= 110% | 125% |
| 100–110% | 100% |
| 85–99.99% | 90% |
| 70–84.99% | 75% |
| 50–69.99% | 50% |
| < 50% | 0% |

### Formula

```
quarterly_bonus_target = salary_monthly × 12 × 0.20 / 4
nb_achievement   = actual_new_business_acv / new_business_target × 100
arr_achievement  = actual_company_arr / arr_target × 100
nb_bonus  = quarterly_bonus_target × 0.80 × tier_payout(nb_achievement)
arr_bonus = quarterly_bonus_target × 0.20 × tier_payout(arr_achievement)
total     = nb_bonus + arr_bonus
```

### Data Sources

| Source | File | Key columns |
|---|---|---|
| Quarterly targets | `data/se_targets.csv` | `year`, `quarter`, `new_business_target_eur`, `arr_target_eur` |
| Actual performance | `data/se_actual_performance.csv` | `year`, `quarter`, `new_business_acv_eur`, `company_arr_eur` |

Finance enters actuals in `se_actual_performance.csv` each quarter. Targets are fixed from the signed FY26 contract.

### Accruals

Finance accruals show `salary_monthly × 0.20` every month (full potential) regardless of actual performance. Actual bonus appears only in the quarter-end month rows.

---

## Key Business Rules

1. **Currency**: commissions are in local currency (SEK/GBP/EUR). ACV stored in EUR; FX from `fx_rates.csv` applied at calculation time. `get_fx_rate()` in `helpers.py`.

2. **Outbound > Inbound**: outbound pays ~2x inbound for SDR fixed rates; 5x for ACV % (5% vs 1%).

3. **6-month SAO account deduplication**: prevents double-paying SDR if same account worked twice within 6 months. Does not apply to CS referrals.

4. **SDR accelerator is a top-up**: only the excess SAOs beyond the 9-threshold get the upgrade. It's `(accelerator_rate − outbound_rate)` extra, not the full accelerator rate.

5. **CS/AM bonus is quarterly**: NRR/CSAT/Credits bonus only appears in Mar/Jun/Sep/Dec rows. Other months show 0 unless referral commissions are present.

6. **CS accruals use full-potential**: Finance accruals = `salary × 0.15` every month regardless of performance.

7. **CS CSAT threshold**: if fewer than 10 CSATs sent in a quarter, entire CSAT measure = 0% regardless of score.

8. **CS NRR targets are per-employee and quarterly-prorated** via 1:1:1:2 split. NRR is always YTD; only the tier threshold shifts each quarter.

9. **Forecast deals don't pay**: deals not yet matched to a NetSuite invoice (`is_forecast=True`) appear in workings but are excluded from `total_commission`.

10. **Stale approval auto-reset**: if commission figures change after approval, `check_and_reset_stale()` auto-reverts to pending.

11. **Plan window enforcement**: `plan_start_date`/`plan_end_date` from Humaans ensure employees only get commission for months they were in the role.

12. **One-off services split**: Add-On deals with `Product Code` starting with `"OO"` → both CSA and AM get **50%** of `Price × Quantity` included in their NRR numerator. OO totals are summed pre-deduplication per opportunity (so mixed OO/non-OO deals are handled correctly). The other 50% is business margin and not modelled. Visible in NRR workings as "One-off svc (50%)".

13. **Multi-year ACV requires CS ownership** (CS plan): CS leads only earn multi-year ACV commission when the Opportunity Owner is a CS employee. AM/AE-owned deals excluded.

14. **Churned account credits excluded**: `_load_credits()` in `pipeline.py` cross-references InputData for Renewal Closed Lost in the same quarter. Period-specific: Q2 churn does not affect Q1 credits.

15. **AE commission is year-end true-up**: no payout in Q1–Q3. Full year calculated in Q4, with quarterly gate applied per-quarter. Annual accelerators apply to total ACV.

16. **SDR Lead is team-only**: no individual deal commissions. Two weighted measures: 35% SAO count, 65% ACV, with tiered payout (0/50/75/100%).

17. **cs_director uses CSLeadCommissionPlan**: same plan, same calculation. The distinction is purely in the job title -> role mapping in Humaans.

18. **AM Lead team aggregate**: `compute_am_lead_nrr()` pools all accounts across all AMs (identified by am/am_lead role) for the lead's NRR score.

19. **SE bonus uses company-level metrics**: both measures (New Business ACV and ARR) are company-wide, not per-employee. Both SEs get the same payout tier for each measure; only the bonus amount differs due to different salaries. Finance enters actuals quarterly in `se_actual_performance.csv`.

20. **SE payout is purely quarterly**: no year-end true-up mechanism in the calculation engine (the contract's "catch-up" language refers to payroll timing, not a separate calculation). 125% tier applies each quarter if achievement > 110%.
