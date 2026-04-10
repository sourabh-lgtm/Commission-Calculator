COMMISSION CALCULATOR — DATA FILES
===================================

Place your CRM exports in this folder. The app reads these files at startup.

FILES REQUIRED
--------------

OPTION A (recommended): Humaans HR Export
  Drop humaans_export.csv in this folder.
  Export from Humaans → People → Export (CSV).
  This is the source of truth for employees, roles, salaries, and managers.
  The app reads it at startup and builds the full employee + salary history tables.
  Note: humaans_export.csv is gitignored (contains employee PII).

  The loader automatically:
  - Determines each employee's CURRENT role from the latest role effective date
  - Determines PLAN START DATE as the first date they held the current commission role
    (so a manager-email-only change doesn't push the plan start forward)
  - Builds a SALARY HISTORY timeline for prorated bonus calculations (AM/CS)
  - Resolves MANAGER relationships via Manager email → Employee ID

  Job title → commission role mapping (src/humaans_loader.py, _TITLE_RULES):
    "Sales Development Representative *"  → sdr  (monthly, fixed rates)
    "Enterprise Sales Development Rep"    → sdr
    "Account Manager / Senior AM"         → am   (quarterly, % of salary)
    "Account Executive / Mid-market AE"   → ae   (quarterly, % of salary)
    "Customer Success *"                  → cs   (quarterly, % of salary)
    "Solutions Engineer / Senior SE"      → se
    "VP Revenue / VP Sales / Head of Sales" → sales_director
    "CFO / Chief Financial Officer"       → cfo
    All other titles                      → other (not commissioned)

OPTION B (fallback): employees.csv
  If humaans_export.csv is not present, the app falls back to a hand-maintained
  employees.csv with the following columns:

1. employees.csv
   Columns: employee_id, name, title, role, region, country, currency,
            manager_id, email, plan_start_date, plan_end_date
   - role: sdr | ae | am | cs | manager | exec | se | cfo | sales_director
   - currency: SEK | GBP | EUR
   - manager_id: references employee_id of the direct manager
   - The name column must match exactly the SDR name in SAO_commission_data.csv
   - Employees with role=cfo or role=sales_director are auto-CC'd on all commission emails

2. SAO_commission_data.csv
   Source: Salesforce CRM report export (direct download, no reformatting needed)
   Required columns: SDR, DCT Discovery, Account Name, Lead Source, Opportunity Name
   Optional columns: Created By, Opportunity Owner, Type, Average ARR Currency,
                     Average ARR, New ACV (converted) Currency, New ACV (converted),
                     Intro Meeting Date

   Processing rules applied automatically:
   - Rows where SDR column is blank → ignored
   - DCT Discovery date (format: DD/MM/YYYY, HH:MM) → determines commission month
   - Intro Meeting Date (format: DD/MM/YYYY) → used for SDR SPIF 8-week window;
     falls back to DCT Discovery date if column is absent or blank
   - Lead Source "Outbound - *" → outbound SAO; "Inbound - *" → inbound SAO
   - Rows with blank/unknown Lead Source → ignored
   - 6-month account deduplication: if the same Account Name already had a
     qualifying SAO within the past 6 months, the second occurrence is excluded
   - SDR name is matched (case-insensitive) to employees.csv name column

3. closed_won.csv
   Columns: close_date, invoice_date, employee_id, opportunity_id, sao_type, acv_eur
   - sao_type: outbound | inbound
   - acv_eur: Annual Contract Value in EUR (base currency)
   - Commission is triggered on invoice_date (not close_date)
   - date format: YYYY-MM-DD

4. cs_book_of_business.csv
   Source: CRM account list export (direct download, no reformatting needed)
   Key columns used (by index): J=Flat Renewal ACV (converted), L=Account ID, T=CSA 2026
   - Provides starting ARR per account and CSA assignment for NRR calculation
   - Account ID: 15-char Salesforce ID (matched to 18-char IDs in InputData)
   - CSA name matched to employee via Humaans name, last-name fallback

5. InputData.csv
   Source: Salesforce opportunities export (direct download, no reformatting needed)
   Key columns: Account Id Casesafe, Type, Stage, Attainment New ACV (converted), Close Date
   - Type="Add-On" → add-on component of NRR
   - Type="Renewal", Stage≠"Closed Lost" → upsell/downsell component
   - Type="Renewal", Stage="Closed Lost" → churn component
   - Close Date format: DD/MM/YYYY
   - NRR is cumulative YTD through the end of each quarter

6. cs_csat_report.csv
   Source: CRM survey-sent report export (direct download, no reformatting needed)
   Columns: Subject, First Name, Last Name, Date, Assigned, Account Name
   - Assigned: CSA full name (matched to employee via Humaans name, last-name fallback)
   - Date format: DD/MM/YYYY
   - Each row = one CSAT survey sent to a contact; multiple rows per account are valid
     and each is counted individually toward the CSA's sent total
   - The app derives csats_sent per employee per quarter automatically (cumulative YTD)
   - Encoding: CP1252 (as exported by CRM)

7. cs_csat_scores_report.csv
   Source: CRM survey-response report export (direct download, no reformatting needed)
   Columns: CSA, Account, Survey Response: Created Date, Survey Response: Survey Response Name, Score
   - CSA: CSA full name (matched to employee via Humaans name, last-name fallback)
   - Score: integer 1–5
   - Date format: DD/MM/YYYY
   - Encoding: CP1252 (as exported by CRM)

8. cs_credits_report.csv
   Source: CRM credit-ledger report export (direct download, no reformatting needed)
   Columns: Credit Ledger Name, Opportunity Product List, Contract Year Start Date,
            Contract Year End Date, Credits Allocated, Credits Used in Contract Year,
            Credit Provisioning Status, Credits Expiring in 90 Days,
            Opportunity: Opportunity Name, Account: CSA: Full Name
   - Account: CSA: Full Name: CSA full name (matched to employee via Humaans name, last-name fallback)
   - Only rows whose Contract Year End Date falls within the commission quarter are included
   - Credits Allocated and Credits Used are summed per CSA per quarter
   - credits_used_pct = Credits Used / Credits Allocated × 100
     (if Credits Allocated = 0 for a CSA, treated as 100% — no credits at risk)
   - Date format: DD/MM/YYYY
   - Encoding: CP1252 (as exported by CRM)

9. fx_rates.csv
   Columns: month, EUR_SEK, EUR_GBP, EUR_USD
   - month: first day of the month, format YYYY-MM-DD
   - Rates used to convert ACV-based commissions from EUR to local currency
   - Update monthly

COMMISSION PAYOUT TIMING
------------------------

  SDR:  Monthly calculation, monthly payout
        - Fixed rates per SAO (outbound/inbound) in local currency (SEK/GBP/EUR)
        - Percentage of ACV on closed won (5% outbound, 1% inbound), FX'd monthly
        - Quarterly accelerator top-up if >9 SAOs in the quarter

  AM / CS:  Quarterly calculation, quarterly payout  [plans coming soon]
        - Bonus = % of annual salary, paid quarterly
        - If salary changes mid-quarter: prorated by calendar days
        - If role changes mid-quarter: each role segment uses its own bonus %
        - Salary history sourced from humaans_export.csv

  AE / SE:  To be defined

FILES AUTO-MANAGED
------------------

10. approval_state.json
   - Tracks approval status for each employee-month (pending/approved/sent)
   - Do NOT edit manually — managed by the application
   - Safe to delete to reset all approval states

NOTES
-----
- All CSV files use comma (,) as delimiter
- Dates must be in YYYY-MM-DD format
- Encoding: UTF-8
