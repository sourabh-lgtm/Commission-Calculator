COMMISSION CALCULATOR — DATA FILES
===================================

Place your CRM exports in this folder. The app reads these files at startup.

FILES REQUIRED
--------------

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
                     Average ARR, New ACV (converted) Currency, New ACV (converted)

   Processing rules applied automatically:
   - Rows where SDR column is blank → ignored
   - DCT Discovery date (format: DD/MM/YYYY, HH:MM) → determines commission month
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

4. fx_rates.csv
   Columns: month, EUR_SEK, EUR_GBP, EUR_USD
   - month: first day of the month, format YYYY-MM-DD
   - Rates used to convert ACV-based commissions from EUR to local currency
   - Update monthly

FILES AUTO-MANAGED
------------------

5. approval_state.json
   - Tracks approval status for each employee-month (pending/approved/sent)
   - Do NOT edit manually — managed by the application
   - Safe to delete to reset all approval states

NOTES
-----
- All CSV files use comma (,) as delimiter
- Dates must be in YYYY-MM-DD format
- Encoding: UTF-8
