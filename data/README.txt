COMMISSION CALCULATOR -- DATA FILES
====================================

Place your CRM/HR exports in this folder. The app reads all files at startup.
For architectural context, see ARCHITECTURE.md and COMMISSION_PLANS.md.

FILES REQUIRED
--------------

OPTION A (recommended): Humaans HR Export
  Drop humaans_export.csv in this folder.
  Export from Humaans -> People -> Export (CSV).
  Source of truth for employees, roles, salaries, and managers.

  The loader (src/humaans_loader.py) automatically:
  - Determines current role from latest role effective date
  - Sets plan_start_date = first date they held the current commissioned role
  - Builds salary history timeline for prorated bonus calculations (AM/CS)
  - Resolves manager relationships via Manager email -> Employee ID

  Job title -> commission role mapping (_TITLE_RULES in humaans_loader.py):
    "Sales Development Representative *"  -> sdr        (monthly, fixed SAO rates)
    "Enterprise Sales Development Rep"    -> sdr
    "SDR Lead", "SDR Team Lead"           -> sdr_lead   (quarterly, team bonus)
    "Account Manager", "Senior AM"        -> am         (quarterly, 20% salary NRR)
    "Account Executive", "Mid-market AE"  -> ae         (annual, 10% ACV)
    "Lead Climate Strategy Expert"        -> cs_lead    (quarterly, 20% salary)
    "Climate Strategy Advisor *"          -> cs         (quarterly, 15% salary)
    "Customer Success *"                  -> customer_success  (not commissioned)
    "Solutions Engineer / Senior SE"      -> se
    "VP Revenue / VP Sales / Head of Sales" -> sales_director  (CC on all emails)
    "CFO / Chief Financial Officer"       -> cfo               (CC on all emails)
    All other titles                      -> other (not commissioned)

OPTION B (fallback): employees.csv
  If humaans_export.csv is not present, the app falls back to employees.csv.
  Columns: employee_id, name, title, role, region, country, currency,
           manager_id, email, plan_start_date, plan_end_date
  - role: sdr | ae | am | am_lead | cs | cs_lead | cs_director | sdr_lead
  - currency: SEK | GBP | EUR
  - The name column must match exactly the SDR name in SAO_commission_data.csv


FILES -- DETAILED SPECIFICATIONS
---------------------------------

1. SAO_commission_data.csv
   Source: Salesforce CRM report export (direct download)
   Required columns: SDR, DCT Discovery, Account Name, Lead Source, Opportunity Name
   Optional columns: Created By, Opportunity Owner, Type, Average ARR Currency,
                     Average ARR, New ACV (converted) Currency, New ACV (converted),
                     Intro Meeting Date

   Processing rules (src/loader.py -> load_sao_commission_data()):
   - Rows where SDR column is blank -> ignored
   - DCT Discovery date (format: DD/MM/YYYY, HH:MM) -> determines commission month
   - Intro Meeting Date (DD/MM/YYYY) -> used for SDR SPIF 8-week window
   - Lead Source "Outbound - *" -> outbound SAO; "Inbound - *" -> inbound SAO
   - Rows with blank/unknown Lead Source -> ignored
   - 6-month account deduplication: same Account Name within past 6 months -> excluded
   - SDR name matched case-insensitively to employee name (last-name fallback)

2. InputData.csv
   Source: Salesforce opportunities export (direct download)
   Key columns: Account Id Casesafe, Opportunity Id Casesafe, Type, Stage,
                Attainment New ACV (converted), Non-Recurring TCV (converted),
                Close Date, Contract Start Date
   - Type="Add-On" -> add-on component of NRR (recurring expansion)
   - Type="Renewal", Stage!="Closed Lost" -> upsell/downsell component
   - Type="Renewal", Stage="Closed Lost" -> churn component (already negative in SF)
   - Close Date format: DD/MM/YYYY
   - NRR is cumulative YTD through end of each quarter
   - Deduplicated by Opportunity Id Casesafe before aggregating (multi-line deals)
   - Account Id Casesafe: 18-char; BoB files use 15-char (matched on first 15 chars)

3. InvoiceSearchCommissions.csv
   Source: NetSuite invoice export
   Used to distinguish actual (invoiced) deals from pipeline forecasts.
   Matched to InputData on Opportunity ID.
   Matched rows -> is_forecast=False; unmatched pipeline deals -> is_forecast=True.

4. fx_rates.csv
   Columns: month, EUR_SEK, EUR_GBP, EUR_USD
   - month: first day of the month, format YYYY-MM-DD
   - Rates used to convert ACV-based commissions from EUR to local currency
   - Update monthly

5. ae_targets.csv
   Columns: employee_id, year, quarterly_target_eur, annual_target_eur, is_ramp_q1
   - One row per AE per year
   - is_ramp_q1: True/False -- if True, Q1 uses ramp plan (see ae_ramp_report.csv)
   - quarterly_target_eur: used for 50% gate per quarter
   - annual_target_eur: used for annual accelerator tiers (12% / 15%)

6. ae_ramp_report.csv
   Source: manually maintained pipeline criteria sheet
   Columns: employee_id, year, quarter, pipeline_value_eur, customers_at_sd_plus,
            multi_threaded_opps, self_generated_pct [and similar]
   - Only used for Q1 when is_ramp_q1=True in ae_targets.csv
   - All 5 criteria must be met for 50% OTE ramp payout

7. sdr_lead_targets.csv
   Columns: employee_id, year, sao_team_target_q, acv_team_target_eur_q, quarterly_bonus_gbp
   - One row per SDR Lead per year
   - sao_team_target_q: team SAO target per quarter (default 54)
   - acv_team_target_eur_q: team closed-won ACV target per quarter (default EUR 223,500)
   - quarterly_bonus_gbp: total quarterly pot (default GBP 2,200)

CS (Climate Strategy) DATA FILES
---------------------------------

8. cs_book_of_business.csv
   Source: CRM account list export (direct download)
   Key columns used (by index):
     Index 5  = Account Name
     Index 9  = Flat Renewal ACV (converted)   -- base ARR per account
     Index 11 = Account ID (15-char Salesforce ID)
     Index 12 = Renewal Date (DD/MM/YYYY)
     Index 19 = CSA 2026                       -- CSA name matched to employees
   - Account ID matched on first 15 chars to 18-char IDs in InputData
   - CSA name matched to employee via Humaans name, last-name fallback

9. cs_nrr_targets.csv
   Columns: employee_id, year, nrr_target_pct
   - One row per CS employee per year
   - nrr_target_pct: annual NRR target (e.g. 96.0)
   - Quarterly targets derived by 1:1:1:2 split (see COMMISSION_PLANS.md)
   - Default = 100% if no row present

10. cs_csat_report.csv
    Source: CRM survey-sent report export
    Columns: Subject, First Name, Last Name, Date, Assigned, Account Name
    - Assigned: CSA full name (matched to employee via last-name fallback)
    - Date format: DD/MM/YYYY
    - Each row = one CSAT survey sent; counted toward CSA's sent total per quarter
    - Encoding: CP1252 (as exported by CRM)

11. cs_csat_scores_report.csv
    Source: CRM survey-response report export
    Columns: CSA, Account, Survey Response: Created Date,
             Survey Response: Survey Response Name, Score
    - CSA: full name (matched to employee)
    - Score: integer 1-5
    - Date format: DD/MM/YYYY
    - Encoding: CP1252

12. cs_credits_report.csv
    Source: CRM credit-ledger report export
    Columns: Credit Ledger Name, Opportunity Product List, Contract Year Start Date,
             Contract Year End Date, Credits Allocated, Credits Used in Contract Year,
             Credit Provisioning Status, Credits Expiring in 90 Days,
             Opportunity: Opportunity Name, Account: CSA: Full Name
    - Only rows whose Contract Year End Date falls within the commission quarter
    - credits_used_pct = Credits Used / Credits Allocated x 100
    - If Credits Allocated = 0, treated as 100% (no credits at risk)
    - Churned account credits auto-excluded (cross-ref InputData for Renewal Closed Lost)
    - Date format: DD/MM/YYYY
    - Encoding: CP1252

13. cs_referrals_report.csv
    Source: Salesforce DCT referral report export
    Key columns: Company Referrer, DCT Discovery, Stage, Amount, Amount Currency, Lead Source
    - Company Referrer: CSA or AM full name
    - DCT Discovery present -> earns SAO commission
    - Stage="Closed Won" -> additionally earns ACV commission
    - Lead Source "Outbound - *" -> outbound rates; else inbound rates
    - Used for both CS and AM referral commissions

AM (Account Manager) DATA FILES
---------------------------------

14. am_book_of_business.csv
    Source: CRM account list export (same format as cs_book_of_business)
    Key columns used (by index):
      Index 5  = Account Name
      Index 9  = Flat Renewal ACV (converted)   -- base ARR per account
      Index 11 = Account ID (15-char Salesforce ID)
      Index 12 = Renewal Date (DD/MM/YYYY)
      Index 18 = Account Owner 2026             -- AM name matched to employees
    - One-off services: 20% of Non-Recurring TCV (vs 50% for CSA)
    - Account ID matched on first 15 chars to 18-char IDs in InputData

15. am_nrr_targets.csv
    Columns: employee_id, year, nrr_target_pct
    - One row per AM per year
    - Same structure and quarterly derivation logic as cs_nrr_targets.csv
    - Default = 100% if no row present


SPIF DATA
----------

16. spif_targets.csv
    Source: manually maintained
    Used by src/spif.py to define SPIF award parameters.
    - SDR SPIF (Q1 2026): flat fee for deals closed within 8 weeks of SAO
    - AE SPIF (Q1 2026): prize for first AE to hit Q1 target before March 1


AUTO-MANAGED FILES
------------------

17. approval_state.json
    - Tracks approval status per employee-month (pending/approved/sent)
    - Do NOT edit manually -- managed by the application
    - Delete to reset all approval states


COMMISSION PAYOUT TIMING SUMMARY
----------------------------------

  SDR:      Monthly. Fixed SAO rates + 5%/1% ACV on closed-won.
            Quarterly accelerator top-up if >9 outbound SAOs in quarter.

  SDR Lead: Quarterly. Team SAO count (35%) + team ACV (65%). GBP 2,200/quarter.

  AE:       Year-end (Q4 only). 10% of 1st-year ACV + 1% multi-year.
            Accelerators: 12% (100-150% target), 15% (>150%).
            Q1 ramp plan available for new hires.

  CS/CS Lead/CS Director:
            Quarterly. 15%/20% of salary.
            Three measures: NRR 50% + CSAT 35% + Credits 15%.
            NRR accelerator: +2% per 1% above target (Q4 CSA; all quarters CS Lead).

  AM/AM Lead:
            Quarterly. 20% of salary.
            Single measure: NRR 100%.
            NRR accelerator: +2% per 1% above target (Q4 only).
            Multi-year ACV: 1% on year-2+ ACV.
            Referral commissions: same rates as CS.


NOTES
------
- All CSV files use comma (,) as delimiter
- Encoding: UTF-8 unless noted otherwise (CSAT files use CP1252)
- Dates: DD/MM/YYYY in Salesforce exports; YYYY-MM-DD in manually maintained files
- Account IDs: BoB files use 15-char Salesforce IDs; InputData uses 18-char
  (matching is done on first 15 characters in cs_nrr_loader.py and am_nrr_loader.py)
