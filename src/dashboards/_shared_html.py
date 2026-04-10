"""Shared HTML fragments injected into every role dashboard."""

SHARED_TABS_HTML = """
<!-- ============================================================ WORKINGS (shared) -->
<div id="tab-workings" class="tab-content">
  <div class="page-title">Commission Workings</div>
  <p class="page-sub">Row-level audit trail for payroll verification</p>
  <div class="controls">
    <label>Employee</label>
    <select id="wk-emp" onchange="loadWorkings()"></select>
    <button class="btn" onclick="previewPDF()">Preview PDF</button>
  </div>
  <div class="kpi-grid" id="wk-kpis"></div>
  <div class="panel">
    <h3>Activity Detail</h3>
    <div class="tbl-wrap"><table id="wk-table"></table></div>
  </div>
</div>

<!-- ============================================================ SPIFs (shared) -->
<div id="tab-spif" class="tab-content">
  <div class="page-title">SPIFs</div>
  <p class="page-sub">Sales Performance Incentive Fund awards</p>
  <div id="spif-body"></div>
</div>

<!-- ============================================================ APPROVE & SEND (shared) -->
<div id="tab-approve-send" class="tab-content">
  <div class="page-title">Approve &amp; Send</div>
  <p class="page-sub">Review, approve and email commission &amp; bonus statements</p>
  <div class="controls">
    <button class="btn primary" onclick="sendAllApproved()" id="as-send-btn">Send All Approved</button>
    <span id="as-counts" style="font-size:12px;color:var(--dim)"></span>
  </div>
  <div class="panel">
    <div class="tbl-wrap"><table id="as-table"></table></div>
  </div>
</div>

<!-- ============================================================ PAYROLL SUMMARY (shared) -->
<div id="tab-payroll-summary" class="tab-content">
  <div class="page-title">Payroll Summary</div>
  <p class="page-sub">Monthly commission per employee — send to payroll for processing</p>
  <div class="controls">
    <label>Year</label>
    <select id="ps-year" onchange="loadPayrollSummary()"></select>
    <button class="btn" onclick="exportPayroll()">Export Excel</button>
    <input type="email" class="search" id="ps-email" placeholder="payroll@company.com" style="width:220px;margin-bottom:0">
    <button class="btn primary" onclick="sendPayroll()">Send to Payroll</button>
  </div>
  <div id="ps-body"></div>
</div>

<!-- ============================================================ FINANCE ACCRUALS (shared) -->
<div id="tab-accrual-summary" class="tab-content">
  <div class="page-title">Finance Accruals</div>
  <p class="page-sub">Department-level commission accruals in local currency — send to finance</p>
  <div class="controls">
    <label>Year</label>
    <select id="ac-year" onchange="loadAccrualSummary()"></select>
    <button class="btn" onclick="exportAccrual()">Export Excel</button>
    <input type="email" class="search" id="ac-email" placeholder="finance@company.com" style="width:220px;margin-bottom:0">
    <button class="btn primary" onclick="sendAccrual()">Send to Finance</button>
  </div>
  <div id="ac-body"></div>
</div>

<!-- ============================================================ DATA VIEW (shared) -->
<div id="tab-data-view" class="tab-content">
  <div class="page-title">Data</div>
  <p class="page-sub">Raw data loaded from CSV files (read-only)</p>
  <div class="controls">
    <label>Table</label>
    <select id="dv-table" onchange="loadDataView()">
      <option value="activities">SDR Activities</option>
      <option value="closed_won">Closed Won</option>
      <option value="employees">Employees</option>
    </select>
    <input type="text" class="search" id="dv-search" placeholder="Search..." oninput="filterDataView()">
  </div>
  <div class="panel">
    <div class="tbl-wrap"><table id="dv-table-el"></table></div>
  </div>
</div>
"""

SHARED_MODALS = """
<div class="modal-overlay" id="pdf-modal">
  <div class="modal">
    <h3>PDF Preview</h3>
    <p class="modal-sub">Opens in a new browser tab.</p>
    <button class="close-btn" onclick="closeModal('pdf-modal')">Close</button>
  </div>
</div>
<div id="toast"></div>
"""
