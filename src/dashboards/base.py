"""Shared HTML/CSS/JS building blocks for all role dashboards."""

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Space Grotesk',system-ui,sans-serif;display:flex;height:100vh;overflow:hidden;background:#fff;color:#000}
:root{--bg:#FFFFFF;--card:#F5F5F5;--border:#E0E0E0;--text:#000;--dim:#595959;--accent:#FF9178;--green:#16a34a;--red:#dc2626;--orange:#ea580c;--purple:#7c3aed;--cyan:#0891b2}
nav{width:220px;min-width:220px;background:#FAFAFA;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow-y:auto}
nav .logo{padding:20px;border-bottom:1px solid var(--border)}
nav .logo small{font-size:8px;font-weight:700;letter-spacing:2px;color:var(--dim);text-transform:uppercase}
nav .logo h1{font-size:17px;font-weight:800;margin-top:2px}
nav .tabs{flex:1;padding:12px 0}
nav .tab{padding:9px 20px;cursor:pointer;font-size:13px;color:var(--dim);border-left:2px solid transparent;transition:all .12s}
nav .tab:hover{color:var(--text)}
nav .tab.active{color:#000;font-weight:700;background:linear-gradient(90deg,rgba(255,145,120,.18),transparent);border-left-color:var(--accent)}
nav .nav-section{font-size:9px;font-weight:700;letter-spacing:1.5px;color:var(--dim);text-transform:uppercase;padding:16px 20px 4px}
nav .global-filter{padding:12px 20px;border-bottom:1px solid var(--border)}
nav .global-filter label{display:block;font-size:9px;font-weight:700;letter-spacing:1.5px;color:var(--dim);text-transform:uppercase;margin-bottom:6px}
nav .global-filter select{width:100%;font-size:12px;padding:6px 10px}
main{flex:1;overflow-y:auto;padding:24px 32px}
.tab-content{display:none}.tab-content.active{display:block}
.page-title{font-size:22px;font-weight:800;margin-bottom:4px}
.page-sub{font-size:13px;color:var(--dim);margin-bottom:20px}
.controls{display:flex;gap:12px;align-items:center;margin-bottom:20px;flex-wrap:wrap}
.controls label{font-size:11px;color:var(--dim);font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-right:4px}
select,input[type=text]{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 14px;color:var(--text);font-size:13px;font-family:inherit;outline:none;cursor:pointer}
select:focus,input:focus{border-color:var(--accent)}
.kpi-grid{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}
.kpi-card{background:var(--card);border-radius:12px;padding:20px 24px;border:1px solid var(--border);flex:1;min-width:170px}
.kpi-card .label{font-size:11px;color:var(--dim);font-weight:600;letter-spacing:.5px;text-transform:uppercase;margin-bottom:6px}
.kpi-card .value{font-size:28px;font-weight:800}
.kpi-card .sub{font-size:12px;color:var(--dim);margin-top:4px}
.panel{background:var(--card);border-radius:12px;padding:20px;border:1px solid var(--border);margin-bottom:20px}
.panel h3{font-size:14px;font-weight:700;margin-bottom:16px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
th{padding:10px 12px;text-align:right;color:var(--dim);font-size:10px;font-weight:600;letter-spacing:.5px;text-transform:uppercase;border-bottom:2px solid var(--border);position:sticky;top:0;background:var(--bg)}
th:first-child{text-align:left}
td{padding:6px 12px;text-align:right;border-bottom:1px solid var(--border)}
td:first-child{text-align:left;font-weight:500}
td.neg{color:var(--red)}td.pos{color:var(--green)}
tr.total td{font-weight:700;background:#EEE;border-top:1px solid var(--border)}
tr.clickable{cursor:pointer;transition:background .1s}
tr.clickable:hover{background:rgba(255,145,120,.1)}
.btn{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:6px 14px;color:var(--text);font-size:11px;font-family:inherit;cursor:pointer;transition:all .12s;font-weight:600}
.btn:hover{background:var(--accent);color:#000;border-color:var(--accent)}
.btn.primary{background:var(--accent);color:#000;border-color:var(--accent)}
.btn.primary:hover{background:#ff7a5a}
.btn.danger{color:var(--red);border-color:var(--red)}
.btn.danger:hover{background:var(--red);color:#fff}
.btn:disabled{opacity:.4;cursor:not-allowed}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.badge.pending{background:#eee;color:var(--dim)}
.badge.approved{background:#fff3e8;color:var(--orange);border:1px solid var(--orange)}
.badge.sent{background:#ecfdf5;color:var(--green);border:1px solid var(--green)}
.progress-wrap{background:var(--border);border-radius:20px;height:8px;margin-top:6px}
.progress-bar{height:8px;border-radius:20px;background:var(--accent);transition:width .3s}
.progress-bar.exceeded{background:var(--green)}
#toast{position:fixed;bottom:24px;right:24px;background:#000;color:#fff;padding:12px 20px;border-radius:10px;font-size:13px;font-weight:600;opacity:0;transition:opacity .3s;z-index:9999;pointer-events:none}
#toast.show{opacity:1}
.modal-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.4);z-index:1000;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{background:#fff;border:1px solid var(--border);border-radius:14px;padding:28px;max-width:640px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 8px 40px rgba(0,0,0,.15)}
.modal h3{font-size:16px;font-weight:700;margin-bottom:4px;color:var(--accent)}
.modal .modal-sub{font-size:12px;color:var(--dim);margin-bottom:16px}
.modal .close-btn{margin-top:16px;background:var(--card);border:1px solid var(--border);color:var(--text);padding:8px 20px;border-radius:8px;cursor:pointer;font-family:inherit;font-size:13px}
.modal .close-btn:hover{background:var(--accent);color:#000;border-color:var(--accent)}
.search{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 14px;color:var(--text);font-size:13px;width:280px;outline:none;margin-bottom:12px;font-family:inherit}
.search:focus{border-color:var(--accent)}
.attain-wrap{display:flex;align-items:center;gap:8px}
.attain-bar-bg{background:var(--border);border-radius:10px;height:6px;width:60px}
.attain-bar{height:6px;border-radius:10px;background:var(--accent)}
.attain-bar.ok{background:var(--green)}
@media(max-width:900px){.two-col{grid-template-columns:1fr}.kpi-grid{flex-direction:column}}
"""

_SHARED_TABS_HTML = """
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

_SHARED_MODALS = """
<div class="modal-overlay" id="pdf-modal">
  <div class="modal">
    <h3>PDF Preview</h3>
    <p class="modal-sub">Opens in a new browser tab.</p>
    <button class="close-btn" onclick="closeModal('pdf-modal')">Close</button>
  </div>
</div>
<div id="toast"></div>
"""

# Shared JavaScript — role-agnostic helpers + shared tab loaders.
# Role-specific modules must define:
#   onRoleInit()  — called after months/employees load; sets up role-specific UI
#   loadTab(name) — called by showTab(); dispatches to role-specific loaders
_SHARED_JS = """
// ============================================================
// State
// ============================================================
let months = [], employees = [], activeTab = '', charts = {};
let dvData = [], dvHeaders = [];

// ============================================================
// Init
// ============================================================
async function init() {
  const [mRes, eRes] = await Promise.all([fetch('/api/months'), fetch('/api/employees')]);
  months = await mRes.json();
  employees = await eRes.json();

  // Populate global month selector
  const gmEl = document.getElementById('global-month');
  months.slice().reverse().forEach(m => {
    const opt = document.createElement('option');
    opt.value = m; opt.text = fmtMonth(m);
    gmEl.appendChild(opt);
  });

  await onRoleInit();
}

// ============================================================
// Global month change
// ============================================================
function onGlobalMonthChange() {
  if (activeTab) loadTab(activeTab);
}

// ============================================================
// Global role filter — navigate to role-specific dashboard
// ============================================================
function onGlobalRoleChange() {
  const role = document.getElementById('global-role').value;
  if (role) window.location.href = '/?role=' + role;
}

function globalRole() {
  return document.getElementById('global-role').value;
}

function filterByRole(arr) {
  const role = globalRole();
  return role ? arr.filter(e => e.role === role) : arr;
}

function rebuildEmpDropdowns() {
  const filtered = filterByRole(employees);
  ['sd-emp','ae-emp','wk-emp'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const prev = el.value;
    el.innerHTML = '';
    filtered.forEach(e => {
      const opt = document.createElement('option');
      opt.value = e.employee_id; opt.text = e.name;
      el.appendChild(opt);
    });
    if (filtered.some(e => e.employee_id === prev)) el.value = prev;
  });
}

// ============================================================
// Tab navigation
// ============================================================
function showTab(name) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  const content = document.getElementById('tab-' + name);
  if (content) content.classList.add('active');
  document.querySelectorAll('.tab').forEach(t => {
    if (t.getAttribute('onclick') && t.getAttribute('onclick').includes("'" + name + "'")) t.classList.add('active');
  });
  activeTab = name;
  loadTab(name);
}

// ============================================================
// Shared tab loaders — Workings, SPIFs, Approve & Send,
//                      Payroll, Accruals, Data
// ============================================================
async function loadWorkings() {
  const empId = document.getElementById('wk-emp').value;
  const month = document.getElementById('global-month').value;
  if (!empId || !month) return;
  const res  = await fetch('/api/commission_workings?employee_id=' + empId + '&month=' + month);
  const data = await res.json();
  const {rows, summary} = data;
  const cur = summary.currency || 'EUR';

  // ---- CS (Climate Strategy Advisor / CS Lead) ----
  if (['cs', 'cs_lead'].includes(globalRole())) {
    const kpiEl = document.getElementById('wk-kpis');
    const refComm = (summary.referral_sao_comm||0) + (summary.referral_cw_comm||0);
    kpiEl.innerHTML =
      kpiCard('Total Payout', fmtAmt(summary.total_commission||0, cur), fmtMonth(month)) +
      kpiCard('NRR Bonus (50%)', fmtAmt(summary.nrr_bonus||0, cur), 'NRR ' + (summary.nrr_pct ? summary.nrr_pct.toFixed(1) + '%' : '\u2014')) +
      kpiCard('CSAT Bonus (35%)', fmtAmt(summary.csat_bonus||0, cur), 'CSAT ' + (summary.csat_score_pct ? summary.csat_score_pct.toFixed(1) + '%' : '\u2014')) +
      kpiCard('Credits Bonus (15%)', fmtAmt(summary.credits_bonus||0, cur), 'Credits ' + (summary.credits_used_pct ? summary.credits_used_pct.toFixed(1) + '%' : '\u2014')) +
      kpiCard('Referral Comm', fmtAmt(refComm, cur), (summary.referral_sao_count||0) + ' referral' + ((summary.referral_sao_count||0) !== 1 ? 's' : '')) +
      ((summary.accelerator_topup||0) > 0 ? kpiCard('NRR Accelerator', fmtAmt(summary.accelerator_topup, cur), 'Top-up') : '');

    // Map quarterly bonus amounts from summary (backend returns commission:null for these rows)
    const bonusAmts = {
      'CS Bonus \u2014 NRR (50%)':             summary.nrr_bonus    || 0,
      'CS Bonus \u2014 CSAT (35%)':            summary.csat_bonus   || 0,
      'CS Bonus \u2014 Service Credits (15%)': summary.credits_bonus || 0,
    };

    // Build custom HTML table for CS workings
    const sym = cur === 'SEK' ? 'kr' : cur === 'GBP' ? '\u00a3' : '\u20ac';
    let tblHtml = '<table style="width:100%;border-collapse:collapse;font-size:12px">';
    tblHtml += '<thead><tr style="background:var(--accent);color:#000">';
    ['Date','Component','Account / Period','Rate / Tier','Amount'].forEach((h,i) => {
      tblHtml += '<th style="padding:8px 12px;text-align:' + (i===4?'right':'left') + ';font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase">' + h + '</th>';
    });
    tblHtml += '</tr></thead><tbody>';

    rows.forEach((r, idx) => {
      const rateDescBase = r.rate_desc || '';
      let rateDesc = rateDescBase;
      if (r.acv_eur) rateDesc = 'ACV ' + fmtAmt(r.acv_eur, 'EUR') + ' \u00d7 ' + (r.fx_rate ? r.fx_rate.toFixed(4) : '1') + ' \u2192 ' + rateDesc;

      if (r.type === 'CS Section') {
        // Full-width section header
        tblHtml += '<tr style="background:#3f3f3f;border-top:2px solid var(--border)">';
        tblHtml += '<td colspan="5" style="padding:7px 12px;font-weight:700;font-size:12px;color:#fff;letter-spacing:.3px">' + (r.opportunity_name || '') + '</td>';
        tblHtml += '</tr>';
      } else if (r.type === 'CS NRR BoB') {
        const amt = r.commission != null ? sym + fmtNum(r.commission) : '\u2014';
        tblHtml += '<tr style="background:#F9FAFB">';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim)"></td>';
        tblHtml += '<td style="padding:5px 12px;font-size:10px;color:var(--dim)">Base BoB</td>';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim)">' + (r.opportunity_name || '') + '</td>';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim);font-size:11px">' + rateDesc + '</td>';
        tblHtml += '<td style="padding:5px 12px;text-align:right;font-weight:700">' + amt + '</td>';
        tblHtml += '</tr>';
      } else if (r.type === 'CS NRR Numerator') {
        const amt = r.commission != null ? sym + fmtNum(r.commission) : '\u2014';
        tblHtml += '<tr style="background:#F9FAFB;border-bottom:2px solid var(--border)">';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim)"></td>';
        tblHtml += '<td style="padding:5px 12px;font-size:10px;color:var(--dim)">NRR Numerator</td>';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim)">' + (r.opportunity_name || '') + '</td>';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim);font-size:11px">' + rateDesc + '</td>';
        tblHtml += '<td style="padding:5px 12px;text-align:right;font-weight:700">' + amt + '</td>';
        tblHtml += '</tr>';
      } else if (r.type === 'CS NRR Account') {
        const net = r.commission != null ? (r.commission >= 0 ? '+' : '') + fmtNum(r.commission) : '\u2014';
        tblHtml += '<tr style="background:#F7F7F7">';
        tblHtml += '<td style="padding:4px 12px;color:var(--dim);font-size:10px"></td>';
        tblHtml += '<td style="padding:4px 12px;color:var(--dim);font-size:10px;padding-left:20px">\u21b3</td>';
        tblHtml += '<td style="padding:4px 12px;color:var(--dim);font-weight:600;font-size:11px">' + (r.opportunity_name || '') + '</td>';
        tblHtml += '<td style="padding:4px 12px;color:var(--dim);font-size:10px">' + rateDesc + '</td>';
        tblHtml += '<td style="padding:4px 12px;text-align:right;color:var(--dim);font-size:11px">' + net + '</td>';
        tblHtml += '</tr>';
      } else if (r.type === 'CS Credits Detail') {
        tblHtml += '<tr style="background:#F7F7F7">';
        tblHtml += '<td style="padding:4px 12px;color:var(--dim);font-size:10px"></td>';
        tblHtml += '<td style="padding:4px 12px;color:var(--dim);font-size:10px;padding-left:20px">\u21b3</td>';
        tblHtml += '<td style="padding:4px 12px;color:var(--dim);font-weight:600;font-size:11px">' + (r.opportunity_name || '') + '</td>';
        tblHtml += '<td style="padding:4px 12px;color:var(--dim);font-size:10px">' + rateDesc + '</td>';
        tblHtml += '<td style="padding:4px 12px;text-align:right;color:var(--dim);font-size:11px">\u2014</td>';
        tblHtml += '</tr>';
      } else if (r.type in bonusAmts) {
        const amt = bonusAmts[r.type];
        const amtStr = amt > 0
          ? '<strong>' + fmtAmt(amt, cur) + '</strong>'
          : '<span style="color:var(--dim)">\u2014</span>';
        tblHtml += '<tr style="background:#FFF3F0">';
        tblHtml += '<td style="padding:6px 12px;font-size:11px">' + (r.date || '') + '</td>';
        tblHtml += '<td style="padding:6px 12px;font-weight:700;color:var(--accent)">' + r.type + '</td>';
        tblHtml += '<td style="padding:6px 12px">' + (r.opportunity_name || '') + '</td>';
        tblHtml += '<td style="padding:6px 12px;font-size:11px;color:var(--dim)">' + rateDesc + '</td>';
        tblHtml += '<td style="padding:6px 12px;text-align:right">' + amtStr + '</td>';
        tblHtml += '</tr>';
      } else {
        // Normal row (referrals, multi-year, etc.)
        let commStr;
        if (r.commission !== null && r.commission !== undefined) {
          commStr = r.is_forecast
            ? '<span style="color:var(--dim)">' + fmtAmt(r.commission, cur) + ' (fcst)</span>'
            : '<strong>' + fmtAmt(r.commission, cur) + '</strong>';
        } else {
          commStr = '\u2014';
        }
        const rowStyle = r.is_forecast ? 'color:var(--dim);font-style:italic' : '';
        tblHtml += '<tr style="' + rowStyle + (idx % 2 === 0 ? 'background:var(--card)' : '') + '">';
        tblHtml += '<td style="padding:6px 12px;font-size:11px">' + (r.date || '') + '</td>';
        tblHtml += '<td style="padding:6px 12px">' + r.type + '</td>';
        tblHtml += '<td style="padding:6px 12px">' + (r.opportunity_name || r.opportunity_id || '') + '</td>';
        tblHtml += '<td style="padding:6px 12px;font-size:11px;color:var(--dim)">' + rateDesc + '</td>';
        tblHtml += '<td style="padding:6px 12px;text-align:right">' + commStr + '</td>';
        tblHtml += '</tr>';
      }
    });

    tblHtml += '</tbody></table>';
    document.getElementById('wk-table').innerHTML = tblHtml;
    return;
  }

  // ---- AE (Account Executive) ----
  if (globalRole() === 'ae') {
    const kpiEl = document.getElementById('wk-kpis');
    const invoicedRows = rows.filter(r => !r.is_forecast);
    const totalAcvFY  = rows.reduce((s,r) => s + (r.acv_eur||0), 0);
    const totalAcvMY  = rows.reduce((s,r) => s + (r.multi_year_acv_eur||0), 0);
    const totalBaseC  = invoicedRows.reduce((s,r) => s + (r.base_commission||0), 0);
    const totalMyC    = invoicedRows.reduce((s,r) => s + (r.my_commission||0), 0);

    kpiEl.innerHTML =
      kpiCard('1st-year ACV', '\u20ac' + fmtNum(totalAcvFY), fmtMonth(month)) +
      kpiCard('Multi-year ACV', '\u20ac' + fmtNum(totalAcvMY), 'Incremental TCV') +
      kpiCard('Base Commission (10%)', fmtAmt(totalBaseC, cur), 'Year-end payment') +
      (totalMyC > 0 ? kpiCard('Multi-yr Commission (1%)', fmtAmt(totalMyC, cur), 'Year-end payment') : '');

    const heads = ['Date','Opportunity','Doc #','Cadence','1st-yr ACV (EUR)','Multi-yr ACV (EUR)','FX','Base Comm (10%)','Multi-yr Comm (1%)','Total'];
    const rowData = rows.map(r => {
      const baseC  = r.base_commission || 0;
      const myC    = r.my_commission   || 0;
      const total  = baseC + myC;
      const isFcst = r.is_forecast;
      const fmt = v => isFcst
        ? '<span style="color:var(--dim)">' + fmtAmt(v, cur) + ' (fcst)</span>'
        : '<strong>' + fmtAmt(v, cur) + '</strong>';
      const cadence = r.invoicing_cadence || '';
      return [
        r.date || '',
        r.opportunity_name || r.opportunity_id || '',
        r.document_number  || '',
        cadence ? '<span style="font-size:11px;color:var(--dim)">' + cadence + '</span>' : '\u2014',
        '\u20ac' + fmtNum(r.acv_eur || 0),
        (r.multi_year_acv_eur||0) > 0 ? '\u20ac' + fmtNum(r.multi_year_acv_eur) : '\u2014',
        r.fx_rate ? r.fx_rate.toFixed(4) : '1.0000',
        fmt(baseC),
        myC > 0 ? fmt(myC) : '\u2014',
        fmt(total),
      ];
    });

    if (!rowData.length) {
      document.getElementById('wk-table').innerHTML =
        '<tr><td colspan="10" style="color:var(--dim);padding:12px">No deals invoiced this month. Commission is paid as a year-end lump sum in December.</td></tr>';
    } else {
      renderTable('wk-table', heads, rowData);
    }
    return;
  }

  // ---- SDR / AE / AM ----
  const kpiEl = document.getElementById('wk-kpis');
  const fcastComm = (summary.outbound_cw_forecast_comm||0) + (summary.inbound_cw_forecast_comm||0);
  const spifAmt   = rows.filter(r => r.type === 'SPIF').reduce((s,r) => s + r.commission, 0);
  kpiEl.innerHTML =
    kpiCard('Confirmed Commission', fmtAmt(summary.total_commission, cur), fmtMonth(month)) +
    kpiCard('Outbound SAOs', summary.outbound_sao_count || 0, fmtAmt(summary.outbound_sao_comm||0,cur)) +
    kpiCard('Inbound SAOs', summary.inbound_sao_count || 0, fmtAmt(summary.inbound_sao_comm||0,cur)) +
    kpiCard('Accelerator', fmtAmt(summary.accelerator_topup||0,cur), 'Quarterly top-up') +
    (spifAmt > 0 ? kpiCard('SPIF', fmtAmt(spifAmt, cur), 'Included in total') : '');

  const heads = ['Date','Type','Opportunity','SAO Type','ACV (EUR)','FX','Rate','Commission'];
  const rowData = rows.map(r => {
    const isForecast = r.is_forecast;
    const isSpif = r.type === 'SPIF';
    const commStr = r.commission !== null
      ? (isForecast
          ? '<span style="color:var(--dim)">' + fmtAmt(r.commission, cur) + ' (fcst)</span>'
          : isSpif
            ? '<strong style="color:var(--purple)">' + fmtAmt(r.commission, cur) + '</strong>'
            : '<strong>' + fmtAmt(r.commission, cur) + '</strong>')
      : '—';
    const typeLabel = isSpif ? '<span style="color:var(--purple);font-weight:700">' + r.type + '</span>' : r.type;
    return [
      r.date, typeLabel,
      r.opportunity_name || r.opportunity_id || '',
      r.sao_type ? r.sao_type.charAt(0).toUpperCase()+r.sao_type.slice(1) : '',
      r.acv_eur ? fmtAmt(r.acv_eur,'EUR') : '—',
      r.fx_rate ? r.fx_rate.toFixed(4) : '—',
      typeLabel, isSpif ? '' : r.rate_desc, commStr
    ];
  });
  renderTable('wk-table', heads, rowData);
}

let approvalData = [];

async function loadSPIFs() {
  const res  = await fetch('/api/spifs');
  let data = await res.json();
  data = filterByRole(data);
  const el = document.getElementById('spif-body');

  if (!data.length) {
    el.innerHTML = '<div class="panel" style="color:var(--dim);font-size:13px">' +
      'No SPIF awards calculated yet.<br><br>' +
      '<strong>AE SPIF:</strong> Fill in <code>data/spif_targets.csv</code> to activate.<br>' +
      '<strong>SDR SPIF:</strong> Awarded automatically for Q1 deals closing within 8 weeks of SAO.' +
      '</div>';
    return;
  }

  const bySpif = {};
  data.forEach(r => { if (!bySpif[r.spif_id]) bySpif[r.spif_id] = []; bySpif[r.spif_id].push(r); });

  let html = '';
  const spifLabels = {
    'sdr_q1_2026_8week': 'SDR Q1 2026 — Closed Won within 8 weeks of SAO',
    'ae_q1_2026_first_to_target': 'AE Q1 2026 — First to Target',
  };

  for (const [spifId, rows] of Object.entries(bySpif)) {
    const label = spifLabels[spifId] || spifId;
    const totalByCur = {};
    rows.forEach(r => { totalByCur[r.currency] = (totalByCur[r.currency]||0) + r.amount; });
    const totalStr = Object.entries(totalByCur).map(([c,a]) => fmtAmt(a,c)).join(' + ');

    html += '<div class="panel" style="margin-bottom:16px"><div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px"><h3>' + label + '</h3><span style="font-size:13px;color:var(--dim)">Total payout: <strong>' + totalStr + '</strong></span></div>';

    if (spifId === 'sdr_q1_2026_8week') {
      const heads = ['SDR','Opportunity','SAO Date','Close Date','Days','Payment Month','Award'];
      const rowData = rows.map(r => [
        r.name, '<span style="font-size:12px">' + r.opportunity + '</span>',
        r.sao_date, r.close_date,
        '<span style="color:' + (r.days_to_close<=28?'var(--green)':r.days_to_close<=42?'var(--orange)':'var(--dim)') + '">' + r.days_to_close + 'd</span>',
        r.payment_month,
        '<strong style="color:var(--green)">' + fmtAmt(r.amount, r.currency) + '</strong>',
      ]);
      html += tableHtml(heads, rowData);
    } else {
      const r = rows[0];
      html += '<div class="kpi-grid">' + kpiCard('Winner \U0001F3C6', r.name, r.currency) + kpiCard('Award', fmtAmt(r.amount, r.currency), 'Paid ' + r.payment_month) + kpiCard('Achievement', r.opportunity, 'Closed by ' + r.close_date) + '</div>';
    }
    html += '</div>';
  }
  el.innerHTML = html;
}

async function loadApprovalStatus() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch('/api/approval_status?month=' + month);
  approvalData = await res.json();
  const displayData = filterByRole(approvalData);

  const pending  = displayData.filter(e => e.status === 'pending').length;
  const approved = displayData.filter(e => e.status === 'approved').length;
  const sent     = displayData.filter(e => e.status === 'sent').length;
  document.getElementById('as-counts').textContent = approved + ' approved \u00b7 ' + sent + ' sent \u00b7 ' + pending + ' pending';

  const isCS     = ['cs', 'cs_lead'].includes(globalRole());
  const isQEnd   = isCS && ['03','06','09','12'].includes(month.slice(5,7));
  const payLabel = isCS ? 'Total Payout' : 'Total Commission';

  // Quarter-end note for CS
  const noteEl = document.getElementById('as-qend-note');
  if (noteEl) noteEl.remove();
  if (isCS && !isQEnd) {
    const note = document.createElement('p');
    note.id = 'as-qend-note';
    note.style.cssText = 'font-size:12px;color:var(--dim);margin-bottom:12px';
    note.textContent = 'Non-quarter-end month \u2014 quarterly bonus (NRR / CSAT / Credits) will be \u20140. Only referral commissions are paid this month.';
    document.querySelector('#tab-approve-send .panel').before(note);
  }

  const heads = ['Name','Region','Currency', payLabel,'Status','Actions'];
  const tbl   = document.getElementById('as-table');
  tbl.innerHTML = '';
  const thead = tbl.createTHead();
  const hr    = thead.insertRow();
  heads.forEach(h => { const th = document.createElement('th'); th.textContent = h; hr.appendChild(th); });
  const tbody = tbl.createTBody();
  displayData.forEach(e => {
    const tr = tbody.insertRow();
    const payoutCell = isCS && !isQEnd && e.total_commission === 0
      ? '<span style="color:var(--dim)">— (no bonus)</span>'
      : '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>';
    tr.innerHTML =
      '<td>' + e.name + '</td>' +
      '<td>' + e.region + '</td>' +
      '<td>' + e.currency + '</td>' +
      '<td style="text-align:right">' + payoutCell + '</td>' +
      '<td style="text-align:center"><span class="badge ' + e.status + '" id="badge-' + e.employee_id + '">' + e.status + '</span></td>' +
      '<td style="text-align:right">' +
        (e.status === 'pending'   ? `<button class="btn" onclick="approveEmp('${e.employee_id}')">Approve</button>` : '') +
        (e.status === 'approved'  ? `<button class="btn danger" onclick="unapproveEmp('${e.employee_id}')">Undo</button>` : '') +
        (e.status !== 'pending'   ? `<button class="btn" style="margin-left:6px" onclick="previewPDFFor('${e.employee_id}')">Preview PDF</button>` : '') +
      '</td>';
  });
}

async function approveEmp(empId) {
  const month = document.getElementById('global-month').value;
  await fetch('/api/approve', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({employee_id:empId,month})});
  toast('Approved \u2713');
  loadApprovalStatus();
}

async function unapproveEmp(empId) {
  const month = document.getElementById('global-month').value;
  await fetch('/api/unapprove', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({employee_id:empId,month})});
  toast('Reverted to pending');
  loadApprovalStatus();
}

async function sendAllApproved() {
  const month = document.getElementById('global-month').value;
  const btn   = document.getElementById('as-send-btn');
  btn.disabled = true; btn.textContent = 'Sending\u2026';
  const res  = await fetch('/api/send_approved', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({month})});
  const data = await res.json();
  btn.disabled = false; btn.textContent = 'Send All Approved';
  if (data.errors && data.errors.length) toast('Sent ' + data.sent + ', ' + data.errors.length + ' error(s) \u2014 check config.ini');
  else toast('\u2713 Sent ' + data.sent + ' statement' + (data.sent !== 1 ? 's' : ''));
  loadApprovalStatus();
}

function previewPDFFor(empId) {
  const month = document.getElementById('global-month').value;
  window.open('/api/preview_pdf?employee_id=' + empId + '&month=' + month, '_blank');
}

function previewPDF() {
  const empId = document.getElementById('wk-emp').value;
  const month = document.getElementById('global-month').value;
  window.open('/api/preview_pdf?employee_id=' + empId + '&month=' + month, '_blank');
}

async function loadPayrollSummary() {
  const yr  = document.getElementById('ps-year').value;
  const res = await fetch('/api/payroll_summary?year=' + yr);
  const data = await res.json();
  const {months: ms, month_labels, regions} = data;
  const el = document.getElementById('ps-body');
  if (!regions || !regions.length) { el.innerHTML = '<div class="panel" style="color:var(--dim)">No data for selected year.</div>'; return; }

  let html = '';
  for (const rd of regions) {
    const emps = rd.employees;
    const qCols = ['Q1','Q2','Q3','Q4'];
    const heads = ['Employee ID','Name','Dept Code','Currency', ...month_labels, ...qCols, 'Total'];
    const totMonthly = Object.fromEntries(ms.map(m => [m, 0]));
    const totQ = {q1:0,q2:0,q3:0,q4:0}; let totTotal = 0;
    const rowData = emps.map(e => {
      ms.forEach(m => totMonthly[m] += e.monthly[m]||0);
      totQ.q1+=e.q1; totQ.q2+=e.q2; totQ.q3+=e.q3; totQ.q4+=e.q4; totTotal+=e.total;
      return [e.employee_id, e.name, e.cost_center_code||'', e.currency,
        ...ms.map(m => fmtAmt(e.monthly[m]||0, e.currency)),
        fmtAmt(e.q1,e.currency), fmtAmt(e.q2,e.currency), fmtAmt(e.q3,e.currency), fmtAmt(e.q4,e.currency),
        '<strong>' + fmtAmt(e.total,e.currency) + '</strong>'];
    });
    const cur = emps.length ? emps[0].currency : 'EUR';
    rowData.push(['', '<strong>TOTAL</strong>', '', cur,
      ...ms.map(m => '<strong>' + fmtAmt(totMonthly[m],cur) + '</strong>'),
      '<strong>' + fmtAmt(totQ.q1,cur) + '</strong>', '<strong>' + fmtAmt(totQ.q2,cur) + '</strong>',
      '<strong>' + fmtAmt(totQ.q3,cur) + '</strong>', '<strong>' + fmtAmt(totQ.q4,cur) + '</strong>',
      '<strong>' + fmtAmt(totTotal,cur) + '</strong>']);
    html += '<div class="panel" style="margin-bottom:20px"><h3>' + rd.region + ' \u2014 ' + yr + '</h3><div class="tbl-wrap">' + tableHtml(heads, rowData) + '</div></div>';
  }
  el.innerHTML = html;
}

function exportPayroll() { window.location.href = '/api/export_payroll?year=' + document.getElementById('ps-year').value; }

async function sendPayroll() {
  const yr = document.getElementById('ps-year').value;
  const email = document.getElementById('ps-email').value.trim();
  if (!email) { toast('Enter a recipient email first'); return; }
  const res  = await fetch('/api/send_payroll', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({year:parseInt(yr),email})});
  const data = await res.json();
  if (data.success) toast('\u2713 Payroll summary sent to ' + email); else toast('\u2717 Error: ' + data.error);
}

async function loadAccrualSummary() {
  const yr  = document.getElementById('ac-year').value;
  const res = await fetch('/api/accrual_summary?year=' + yr);
  const data = await res.json();
  const {months: ms, month_labels, regions} = data;
  const el = document.getElementById('ac-body');
  if (!regions || !regions.length) { el.innerHTML = '<div class="panel" style="color:var(--dim)">No data for selected year.</div>'; return; }

  let html = '';
  for (const rd of regions) {
    const rows = rd.rows;
    const qCols = ['Q1','Q2','Q3','Q4'];
    const heads = ['Employee ID','Name','Dept Code','Type','Currency', ...month_labels, ...qCols, 'Total'];
    const totMonthly = Object.fromEntries(ms.map(m => [m, 0]));
    const totQ = {q1:0,q2:0,q3:0,q4:0}; let totTotal = 0;
    const contMonthly = Object.fromEntries(ms.map(m => [m, 0]));
    const contQ = {q1:0,q2:0,q3:0,q4:0}; let contTotal = 0;
    const regionCurrency = (rows.find(r => !['Employer NI (13.8%)', 'Employer Social Contributions (31%)'].includes(r.type)) || {}).currency || 'EUR';
    const _EMPLOYER_TYPES = ['Employer NI (13.8%)', 'Employer Social Contributions (31%)'];
    const rowData = rows.map(r => {
      const isEmployerContrib = _EMPLOYER_TYPES.includes(r.type);
      const cur  = r.currency || regionCurrency;
      if (!isEmployerContrib) { ms.forEach(m => totMonthly[m] += r.monthly[m]||0); totQ.q1+=r.q1; totQ.q2+=r.q2; totQ.q3+=r.q3; totQ.q4+=r.q4; totTotal+=r.total; }
      else                    { ms.forEach(m => contMonthly[m] += r.monthly[m]||0); contQ.q1+=r.q1; contQ.q2+=r.q2; contQ.q3+=r.q3; contQ.q4+=r.q4; contTotal+=r.total; }
      const style = isEmployerContrib ? 'color:var(--dim);font-style:italic' : '';
      const fmt = v => isEmployerContrib ? '<span style="' + style + '">' + fmtAmt(v, cur) + '</span>' : fmtAmt(v, cur);
      return [
        '<span style="' + style + '">' + r.employee_id + '</span>',
        '<span style="' + style + '">' + r.name + '</span>',
        '<span style="' + style + '">' + (r.cost_center_code||'') + '</span>',
        '<span style="' + style + '">' + r.type + '</span>',
        '<span style="' + style + '">' + cur + '</span>',
        ...ms.map(m => fmt(r.monthly[m]||0)),
        fmt(r.q1), fmt(r.q2), fmt(r.q3), fmt(r.q4),
        isEmployerContrib ? fmt(r.total) : '<strong>' + fmtAmt(r.total, cur) + '</strong>'
      ];
    });
    rowData.push(['', '<strong>TOTAL (Commission)</strong>', '', '', '',
      ...ms.map(m => '<strong>' + fmtAmt(totMonthly[m], regionCurrency) + '</strong>'),
      '<strong>' + fmtAmt(totQ.q1, regionCurrency) + '</strong>', '<strong>' + fmtAmt(totQ.q2, regionCurrency) + '</strong>',
      '<strong>' + fmtAmt(totQ.q3, regionCurrency) + '</strong>', '<strong>' + fmtAmt(totQ.q4, regionCurrency) + '</strong>',
      '<strong>' + fmtAmt(totTotal, regionCurrency) + '</strong>']);
    if (contTotal > 0) rowData.push(['', '<strong>TOTAL (Employer Contributions)</strong>', '', '', '',
      ...ms.map(m => '<strong>' + fmtAmt(contMonthly[m], regionCurrency) + '</strong>'),
      '<strong>' + fmtAmt(contQ.q1, regionCurrency) + '</strong>', '<strong>' + fmtAmt(contQ.q2, regionCurrency) + '</strong>',
      '<strong>' + fmtAmt(contQ.q3, regionCurrency) + '</strong>', '<strong>' + fmtAmt(contQ.q4, regionCurrency) + '</strong>',
      '<strong>' + fmtAmt(contTotal, regionCurrency) + '</strong>']);
    html += '<div class="panel" style="margin-bottom:20px"><h3>' + rd.region + ' \u2014 FY' + yr + ' (' + regionCurrency + ')</h3><div class="tbl-wrap">' + tableHtml(heads, rowData) + '</div></div>';
  }
  el.innerHTML = html;
}

function exportAccrual() { window.location.href = '/api/export_accrual?year=' + document.getElementById('ac-year').value; }

async function sendAccrual() {
  const yr = document.getElementById('ac-year').value;
  const email = document.getElementById('ac-email').value.trim();
  if (!email) { toast('Enter a recipient email first'); return; }
  const res  = await fetch('/api/send_accrual', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({year:parseInt(yr),email})});
  const data = await res.json();
  if (data.success) toast('\u2713 Accrual summary sent to ' + email); else toast('\u2717 Error: ' + data.error);
}

async function loadDataView() {
  const tbl = document.getElementById('dv-table').value;
  const month = months[months.length-1] || '';
  const res = tbl === 'employees'
    ? await fetch('/api/employees')
    : await fetch('/api/team_overview?month=' + month);
  if (tbl === 'employees') dvData = await res.json();
  else { const d = await res.json(); dvData = d.employees || []; }
  dvHeaders = dvData.length ? Object.keys(dvData[0]) : [];
  renderDVTable(dvData);
}

function filterDataView() {
  const q = document.getElementById('dv-search').value.toLowerCase();
  renderDVTable(dvData.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(q))));
}

function renderDVTable(data) {
  const tbl = document.getElementById('dv-table-el');
  if (!data.length) { tbl.innerHTML = '<tr><td>No data</td></tr>'; return; }
  const heads = Object.keys(data[0]);
  renderTable('dv-table-el', heads, data.map(r => heads.map(h => r[h] ?? '')));
}

// ============================================================
// Chart helpers
// ============================================================
const PALETTE = ['#FF9178','#16a34a','#7c3aed','#ea580c','#0891b2','#db2777'];

function renderBar(id, labels, data, label, color) {
  color = color || '#FF9178';
  if (charts[id]) charts[id].destroy();
  const ctx = document.getElementById(id).getContext('2d');
  charts[id] = new Chart(ctx, {
    type:'bar',
    data:{labels,datasets:[{label,data,backgroundColor:color+'CC',borderRadius:6}]},
    options:{responsive:true,plugins:{legend:{display:false}},
      scales:{x:{ticks:{color:'#595959',font:{size:10,family:'Space Grotesk'}}},
              y:{ticks:{color:'#595959',font:{size:10}},grid:{color:'#E0E0E0'}}}}
  });
}

function renderLine(id, labels, data, label) {
  if (charts[id]) charts[id].destroy();
  const ctx = document.getElementById(id).getContext('2d');
  charts[id] = new Chart(ctx, {
    type:'line',
    data:{labels,datasets:[{label,data,borderColor:'#FF9178',backgroundColor:'rgba(255,145,120,.12)',tension:.3,fill:true,pointRadius:4,pointBackgroundColor:'#FF9178'}]},
    options:{responsive:true,plugins:{legend:{display:false}},
      scales:{x:{ticks:{color:'#595959',font:{size:10,family:'Space Grotesk'}}},
              y:{ticks:{color:'#595959',font:{size:10}},grid:{color:'#E0E0E0'}}}}
  });
}

// ============================================================
// Table helpers
// ============================================================
function renderTable(id, heads, rows) {
  const tbl = document.getElementById(id);
  let html = '<thead><tr>' + heads.map(h => '<th>' + h + '</th>').join('') + '</tr></thead><tbody>';
  rows.forEach(r => {
    html += '<tr>' + r.map((v,j) => '<td' + (j>0?' style="text-align:right"':'') + '>' + (v??'') + '</td>').join('') + '</tr>';
  });
  html += '</tbody>';
  tbl.innerHTML = html;
}

function tableHtml(heads, rows) {
  let h = '<div style="overflow-x:auto"><table class="data-table"><thead><tr>';
  heads.forEach(hd => h += '<th>' + hd + '</th>');
  h += '</tr></thead><tbody>';
  rows.forEach(row => { h += '<tr>'; row.forEach(cell => h += '<td>' + (cell ?? '') + '</td>'); h += '</tr>'; });
  h += '</tbody></table></div>';
  return h;
}

// ============================================================
// Formatting helpers
// ============================================================
function fmtMonth(s) {
  if (!s) return '';
  const d = new Date(s);
  return d.toLocaleDateString('en-GB',{month:'short',year:'2-digit'}).replace(' ','\u00b7');
}

function fmtNum(v) {
  const n = parseFloat(v);
  if (isNaN(n)) return '\u2014';
  return n.toLocaleString('en-GB', {minimumFractionDigits: 0, maximumFractionDigits: 0});
}

function fmtAmt(v, currency) {
  if (v === null || v === undefined) return '\u2014';
  const n = parseFloat(v);
  if (isNaN(n)) return '\u2014';
  if (currency === 'mixed') return n.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
  const syms = {SEK:'kr',GBP:'\u00a3',EUR:'\u20ac',USD:'$'};
  const sym  = syms[currency] || '';
  if (currency === 'SEK') return n.toLocaleString('sv-SE',{minimumFractionDigits:0,maximumFractionDigits:0}) + ' kr';
  return sym + n.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
}

function kpiCard(label, value, sub) {
  return '<div class="kpi-card"><div class="label">' + label + '</div><div class="value">' + value + '</div>' + (sub ? '<div class="sub">' + sub + '</div>' : '') + '</div>';
}

function attainCell(pct) {
  const w = Math.min(100, pct);
  const cls = pct >= 100 ? 'ok' : '';
  return '<div class="attain-wrap"><span style="font-size:12px;font-weight:600' + (pct>=100?';color:var(--green)':'') + '">' + pct + '%</span><div class="attain-bar-bg"><div class="attain-bar ' + cls + '" style="width:' + w + '%"></div></div></div>';
}

// ============================================================
// Toast / Modal / CSV export
// ============================================================
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

function closeModal(id) { document.getElementById(id).classList.remove('open'); }

function exportCSV(tab) {
  const tbl = document.querySelector('#tab-' + tab + ' table');
  if (!tbl) return;
  const rows = [...tbl.querySelectorAll('tr')].map(r =>
    [...r.querySelectorAll('th,td')].map(c => '"' + c.innerText.replace(/"/g,'""') + '"').join(',')
  );
  const blob = new Blob([rows.join('\\n')], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'commission_' + tab + '_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}

init();
"""


def _role_options_html(selected_role: str) -> str:
    roles = [
        ("sdr", "SDR"),
        ("cs",  "Climate Strategy Advisor"),
        ("ae",  "Account Executive"),
        ("am",  "Account Manager"),
    ]
    return "".join(
        f'<option value="{v}"{" selected" if v == selected_role else ""}>{label}</option>'
        for v, label in roles
    )


def assemble_html(
    role: str,
    title: str,
    nav_links: str,
    role_tabs_html: str,
    role_js: str,
) -> str:
    role_opts = _role_options_html(role)
    return (
        f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>{_CSS}</style>
</head>
<body>

<nav>
  <div class="logo">
    <small>Normative</small>
    <h1>Commissions</h1>
  </div>
  <div class="global-filter">
    <label>Month</label>
    <select id="global-month" onchange="onGlobalMonthChange()"></select>
  </div>
  <div class="global-filter" style="margin-top:8px">
    <label>Role</label>
    <select id="global-role" onchange="onGlobalRoleChange()">
      {role_opts}
    </select>
  </div>
  <div class="tabs">
    {nav_links}
  </div>
</nav>

<main>
{role_tabs_html}
{_SHARED_TABS_HTML}
</main>

{_SHARED_MODALS}

<script>
{role_js}
{_SHARED_JS}
</script>
</body>
</html>"""
    )
