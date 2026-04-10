"""Account Executive dashboard — full implementation."""
from src.dashboards.base import assemble_html

_NAV_LINKS = """
    <div class="nav-section">Team</div>
    <div class="tab active" onclick="showTab('ae-overview')">Team Overview</div>
    <div class="tab" onclick="showTab('ae-monthly')">Monthly Performance</div>
    <div class="tab" onclick="showTab('ae-quarterly')">Quarterly Performance</div>
    <div class="tab" onclick="showTab('ae-annual')">Annual Summary</div>
    <div class="nav-section">Individual</div>
    <div class="tab" onclick="showTab('ae-detail')">AE Detail</div>
    <div class="tab" onclick="showTab('workings')">Commission Workings</div>
    <div class="nav-section">Actions</div>
    <div class="tab" onclick="showTab('approve-send')">Approve &amp; Send</div>
    <div class="tab" onclick="showTab('payroll-summary')">Payroll Summary</div>
    <div class="tab" onclick="showTab('accrual-summary')">Finance Accruals</div>
    <div class="tab" onclick="showTab('data-view')">Data</div>
"""

_TABS_HTML = """
<!-- ============================================================ AE TEAM OVERVIEW -->
<div id="tab-ae-overview" class="tab-content active">
  <div class="page-title">Team Overview</div>
  <p class="page-sub">Account Executive ACV pipeline &amp; year-end commission</p>
  <div class="controls">
    <label>Year</label>
    <select id="ae-year" onchange="loadAEOverview()"></select>
    <button class="btn" onclick="exportCSV('ae-overview')">Export CSV</button>
  </div>
  <div class="kpi-grid" id="ae-to-kpis"></div>
  <div class="panel">
    <h3>ACV by AE</h3>
    <canvas id="ae-chart-acv" height="120"></canvas>
  </div>
  <div class="panel">
    <h3>AE Breakdown</h3>
    <div class="tbl-wrap"><table id="ae-to-table"></table></div>
  </div>
</div>

<!-- ============================================================ AE MONTHLY PERFORMANCE -->
<div id="tab-ae-monthly" class="tab-content">
  <div class="page-title">Monthly Performance</div>
  <p class="page-sub">ACV closed per AE for the selected month</p>
  <div class="controls">
    <button class="btn" onclick="exportCSV('ae-monthly')">Export CSV</button>
  </div>
  <div class="kpi-grid" id="ae-mo-kpis"></div>
  <div class="panel">
    <h3>ACV by AE</h3>
    <canvas id="ae-chart-mo" height="120"></canvas>
  </div>
  <div class="panel">
    <h3>Monthly Breakdown</h3>
    <div class="tbl-wrap"><table id="ae-mo-table"></table></div>
  </div>
</div>

<!-- ============================================================ AE QUARTERLY PERFORMANCE -->
<div id="tab-ae-quarterly" class="tab-content">
  <div class="page-title">Quarterly Performance</div>
  <p class="page-sub">ACV vs target and gate status by quarter</p>
  <div class="controls">
    <label>Year</label>
    <select id="ae-q-year" onchange="loadAEQuarterly()"></select>
    <label>Quarter</label>
    <select id="ae-q-quarter" onchange="loadAEQuarterly()">
      <option value="1">Q1</option>
      <option value="2">Q2</option>
      <option value="3">Q3</option>
      <option value="4">Q4</option>
    </select>
    <button class="btn" onclick="exportCSV('ae-quarterly')">Export CSV</button>
  </div>
  <div class="kpi-grid" id="ae-q-kpis"></div>
  <div class="panel">
    <h3>ACV Progress to Target</h3>
    <div id="ae-q-progress"></div>
  </div>
  <div class="panel">
    <h3>Quarterly Breakdown</h3>
    <div class="tbl-wrap"><table id="ae-q-table"></table></div>
  </div>
</div>

<!-- ============================================================ AE ANNUAL SUMMARY -->
<div id="tab-ae-annual" class="tab-content">
  <div class="page-title">Annual Summary</div>
  <p class="page-sub">Full year ACV &amp; commission breakdown per AE</p>
  <div class="controls">
    <label>Year</label>
    <select id="ae-ann-year" onchange="loadAEAnnual()"></select>
  </div>
  <div class="panel">
    <h3>Annual Commission Summary</h3>
    <div class="tbl-wrap"><table id="ae-ann-table"></table></div>
  </div>
</div>

<!-- ============================================================ AE DETAIL -->
<div id="tab-ae-detail" class="tab-content">
  <div class="page-title">AE Detail</div>
  <p class="page-sub">Per-quarter performance &amp; gate status for an individual AE</p>
  <div class="controls">
    <label>AE</label>
    <select id="ae-emp" onchange="loadAEDetail()"></select>
    <label>Year</label>
    <select id="ae-det-year" onchange="loadAEDetail()"></select>
  </div>
  <div class="kpi-grid" id="ae-det-kpis"></div>
  <div class="panel">
    <h3>Annual ACV Progress</h3>
    <div id="ae-det-progress"></div>
  </div>
  <div class="panel">
    <h3>Quarterly Breakdown</h3>
    <div class="tbl-wrap"><table id="ae-det-table"></table></div>
  </div>
  <div id="ae-det-commission" class="panel" style="display:none">
    <h3>Commission Breakdown</h3>
    <div class="tbl-wrap"><table id="ae-det-comm-table"></table></div>
  </div>
</div>
"""

_ROLE_JS = """
// ============================================================
// AE — role init + tab dispatch
// ============================================================
async function onRoleInit() {
  const curYr = new Date().getFullYear();

  // Populate year selectors
  ['ae-year', 'ae-ann-year', 'ae-det-year', 'ae-q-year', 'ps-year', 'ac-year'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    [curYr - 1, curYr, curYr + 1].forEach(y => {
      const opt = document.createElement('option');
      opt.value = y; opt.text = y;
      if (y === curYr) opt.selected = true;
      el.appendChild(opt);
    });
  });

  // Set default quarter
  const curQ = Math.ceil((new Date().getMonth() + 1) / 3);
  const qEl = document.getElementById('ae-q-quarter');
  if (qEl) qEl.value = curQ;

  // Populate AE employee dropdown
  rebuildEmpDropdowns();

  showTab('ae-overview');
}

function loadTab(name) {
  if (name === 'ae-overview')       loadAEOverview();
  else if (name === 'ae-monthly')    loadAEMonthly();
  else if (name === 'ae-quarterly')  loadAEQuarterly();
  else if (name === 'ae-annual')    loadAEAnnual();
  else if (name === 'ae-detail')    loadAEDetail();
  else if (name === 'workings')     loadWorkings();
  else if (name === 'approve-send') loadApprovalStatus();
  else if (name === 'payroll-summary')  loadPayrollSummary();
  else if (name === 'accrual-summary')  loadAccrualSummary();
  else if (name === 'data-view')    loadDataView();
}

// ============================================================
// AE Team Overview
// ============================================================
async function loadAEOverview() {
  const yr  = document.getElementById('ae-year').value;
  const res = await fetch('/api/ae_overview?year=' + yr);
  const data = await res.json();
  const {employees: emps, kpis} = data;

  // KPI cards
  document.getElementById('ae-to-kpis').innerHTML =
    kpiCard('Total YTD ACV', '\u20ac' + fmtNum(kpis.total_acv_eur), 'EUR') +
    kpiCard('Team Avg Attainment', kpis.avg_attainment_pct + '%', 'Annual target') +
    kpiCard('Year-end Commission', '\u20ac' + fmtNum(kpis.total_year_end_comm_eur), 'EUR') +
    kpiCard('Active AEs', kpis.num_aes, 'FY' + yr);

  // Bar chart
  const labels = emps.map(e => e.name.split(' ')[0]);
  renderBar('ae-chart-acv', labels, emps.map(e => e.ytd_acv_eur), 'YTD ACV (EUR)');

  // Table
  const heads = ['Name', 'Region', 'Cur',
    'Q1 ACV', 'Q1 Gate', 'Q2 ACV', 'Q2 Gate',
    'Q3 ACV', 'Q3 Gate', 'Q4 ACV', 'Q4 Gate',
    'Annual ACV', 'vs Target', 'Year-end Comm'];

  const rows = emps.map(e => {
    const attColor = e.annual_attainment_pct >= 100
      ? 'var(--green)' : e.annual_attainment_pct >= 50
      ? 'var(--orange)' : 'var(--red)';
    return [
      e.name, e.region, e.currency,
      '\u20ac' + fmtNum(e.q1_acv), gateIcon(e.q1_gate),
      '\u20ac' + fmtNum(e.q2_acv), gateIcon(e.q2_gate),
      '\u20ac' + fmtNum(e.q3_acv), gateIcon(e.q3_gate),
      '\u20ac' + fmtNum(e.q4_acv), gateIcon(e.q4_gate),
      '<strong>\u20ac' + fmtNum(e.ytd_acv_eur) + '</strong>',
      '<span style="color:' + attColor + ';font-weight:600">' + e.annual_attainment_pct + '%</span>',
      e.year_end_commission > 0
        ? '<strong>' + fmtAmt(e.year_end_commission, e.currency) + '</strong>'
        : '<span style="color:var(--dim)">\u2014</span>',
    ];
  });
  renderTable('ae-to-table', heads, rows);
}

// ============================================================
// AE Annual Summary
// ============================================================
async function loadAEAnnual() {
  const yr  = document.getElementById('ae-ann-year').value;
  const res = await fetch('/api/ae_overview?year=' + yr);
  const data = await res.json();
  const {employees: emps} = data;

  const heads = ['Name', 'Region', 'Cur', 'Annual Target EUR', 'YTD ACV EUR',
    'Attainment %', 'Qualifying ACV', 'Year-end Comm (local)', 'Year-end Comm (EUR)'];

  const rows = emps.map(e => {
    const attColor = e.annual_attainment_pct >= 100
      ? 'var(--green)' : e.annual_attainment_pct >= 50
      ? 'var(--orange)' : 'var(--red)';
    return [
      e.name, e.region, e.currency,
      '\u20ac' + fmtNum(e.annual_target_eur),
      '\u20ac' + fmtNum(e.ytd_acv_eur),
      '<span style="color:' + attColor + ';font-weight:600">' + e.annual_attainment_pct + '%</span>',
      '\u20ac' + fmtNum(e.qualifying_acv_eur),
      e.year_end_commission > 0
        ? '<strong>' + fmtAmt(e.year_end_commission, e.currency) + '</strong>'
        : '<span style="color:var(--dim)">\u2014</span>',
      e.year_end_commission_eur > 0
        ? '<strong>\u20ac' + fmtNum(e.year_end_commission_eur) + '</strong>'
        : '<span style="color:var(--dim)">\u2014</span>',
    ];
  });
  renderTable('ae-ann-table', heads, rows);
}

// ============================================================
// AE Detail
// ============================================================
async function loadAEDetail() {
  const empId = document.getElementById('ae-emp').value;
  const yr    = document.getElementById('ae-det-year').value;
  if (!empId) return;

  const res  = await fetch('/api/ae_detail?employee_id=' + empId + '&year=' + yr);
  const data = await res.json();
  const {employee: emp, quarters, year_end, all_accelerators} = data;
  const cur  = emp.currency || 'EUR';

  // KPI cards
  const commAmt = emp.year_end_commission || 0;
  const attColor = (emp.annual_attainment_pct || 0) >= 100
    ? 'var(--green)' : (emp.annual_attainment_pct || 0) >= 50
    ? 'var(--orange)' : 'var(--red)';

  const accList = all_accelerators || ((year_end && year_end.all_accelerators) ? year_end.all_accelerators : []);
  const acc = (year_end && year_end.accelerator) ? year_end.accelerator : (accList.length ? accList[accList.length-1] : {});
  const finalQ = acc.quarter || 4;
  const qMonthNames = {1: 'March', 2: 'June', 3: 'September', 4: 'December'};
  const commMonthLabel = commAmt > 0 ? 'Paid quarterly' : 'Not yet paid';

  document.getElementById('ae-det-kpis').innerHTML =
    kpiCard('Annual Target', '\u20ac' + fmtNum(emp.annual_target_eur || 0), 'EUR') +
    kpiCard('YTD ACV', '\u20ac' + fmtNum(emp.ytd_acv_eur || 0), 'EUR') +
    kpiCard('Attainment', '<span style="color:' + attColor + '">' + (emp.annual_attainment_pct || 0) + '%</span>', 'vs annual target') +
    kpiCard('Commission', fmtAmt(commAmt, cur), commAmt > 0 ? 'Paid in ' + commMonthLabel : 'Not yet paid');

  // Progress bar
  const target = emp.annual_target_eur || 1;
  const acv    = emp.ytd_acv_eur || 0;
  const pct50  = 50;
  const pct100 = 100;
  const pctACV = Math.min(150, (acv / target) * 100);
  const barColor = acv >= target ? 'var(--green)' : acv >= target * 0.5 ? 'var(--accent)' : 'var(--red)';

  document.getElementById('ae-det-progress').innerHTML =
    '<div style="position:relative;margin-bottom:8px">' +
      '<div style="background:var(--border);border-radius:10px;height:18px;position:relative">' +
        '<div style="background:' + barColor + ';width:' + pctACV + '%;height:18px;border-radius:10px;transition:width .4s"></div>' +
        '<div style="position:absolute;top:0;left:' + pct50 + '%;height:18px;width:2px;background:var(--dim);opacity:.6"></div>' +
        '<div style="position:absolute;top:0;left:' + Math.min(100, pct100) + '%;height:18px;width:2px;background:#000;opacity:.4"></div>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--dim);margin-top:4px">' +
        '<span>0</span>' +
        '<span style="position:absolute;left:' + pct50 + '%">50% gate</span>' +
        '<span style="position:absolute;left:' + Math.min(99, pct100) + '%">100%</span>' +
        '<span>\u20ac' + fmtNum(target) + '</span>' +
      '</div>' +
    '</div>';

  // Quarterly table
  const heads = ['Quarter', 'Q ACV (EUR)', 'Q Target (EUR)', 'Attainment', 'Gate Met', 'Ramp Status', 'Total Deals', 'Invoiced', 'Forecast'];
  const rows = (quarters || []).map(q => {
    const gateStr = q.gate_met
      ? '<span style="color:var(--green);font-weight:700">\u2713 Met</span>'
      : '<span style="color:var(--red);font-weight:700">\u2717 Not Met</span>';
    const attColor2 = q.q_attainment_pct >= 100
      ? 'var(--green)' : q.q_attainment_pct >= 50
      ? 'var(--orange)' : 'var(--red)';
    // Look up ramp result from the accelerator list for this quarter
    const qAcc = accList.find(a => a.quarter === q.quarter);
    let rampCell = '<span style="color:var(--dim)">\u2014</span>';
    if (qAcc && qAcc.ramp_passed === true) {
      rampCell = '<span style="color:var(--green);font-weight:700">\u2713 Ramp Earned</span>';
    } else if (qAcc && qAcc.ramp_passed === false) {
      rampCell = '<span style="color:var(--red);font-weight:700">\u2717 Not Met</span>';
    }
    return [
      q.q_label,
      '\u20ac' + fmtNum(q.q_acv_eur),
      '\u20ac' + fmtNum(q.q_target_eur),
      '<span style="color:' + attColor2 + ';font-weight:600">' + q.q_attainment_pct + '%</span>',
      gateStr,
      rampCell,
      q.deals_count,
      q.invoiced_count,
      q.forecast_count,
    ];
  });
  renderTable('ae-det-table', heads, rows);

  // Commission breakdown panel — one row per qualifying quarter
  const commPanel = document.getElementById('ae-det-commission');
  if (accList.length > 0) {
    const sym = cur === 'GBP' ? '\u00a3' : cur === 'SEK' ? 'kr' : '\u20ac';
    const bHeads = ['Quarter', 'Gate', 'Ramp', 'Qualifying ACV (EUR)', 'Base Comm (10%)', 'Multi-yr Comm (1%)', 'Ramp Bonus (50% OTE)', 'Accel Tier1 (12%)', 'Accel Tier2 (15%)', 'Total Payout (' + cur + ')'];
    const bRows = accList.map(a => {
      const fx   = a.fx_rate || 1;
      const fmtL = v => (v && v > 0) ? sym + fmtNum(v) : '\u2014';
      const fmtE = v => (v && v > 0) ? '\u20ac' + fmtNum(v / fx) : '\u2014';
      const qLbl = 'Q' + a.quarter + ' FY' + String(a.year || yr).slice(2);
      const gateStr = a.gate_met
        ? '<span style="color:var(--green);font-weight:700">\u2713</span>'
        : '<span style="color:var(--red);font-weight:700">\u2717</span>';
      let rampStr = '<span style="color:var(--dim)">\u2014</span>';
      if (a.ramp_passed === true) {
        rampStr = '<span style="color:var(--green);font-weight:700">\u2713 Earned</span>';
      } else if (a.ramp_passed === false) {
        rampStr = '<span style="color:var(--red);font-weight:700">\u2717 Not met</span>';
      }
      return [
        qLbl, gateStr, rampStr,
        fmtE(a.qualifying_acv_eur),
        fmtL(a.base_commission),
        fmtL(a.multi_year_commission),
        fmtL(a.ramp_bonus),
        fmtL(a.accelerator_1),
        fmtL(a.accelerator_2),
        '<strong>' + fmtL(a.accelerator_topup) + '</strong>',
      ];
    });
    // Grand total row
    const totalTopup = accList.reduce((s,a) => s + (a.accelerator_topup||0), 0);
    bRows.push(['<strong>Total</strong>', '', '', '', '', '', '', '', '',
      '<strong>' + sym + fmtNum(totalTopup) + '</strong>']);
    renderTable('ae-det-comm-table', bHeads, bRows);
    commPanel.style.display = '';
  } else {
    commPanel.style.display = 'none';
  }
}

// ============================================================
// AE Monthly Performance
// ============================================================
async function loadAEMonthly() {
  const month = document.getElementById('global-month').value;
  if (!month) return;
  const yr = month.substring(0, 4);
  const res = await fetch('/api/ae_monthly?year=' + yr);
  const data = await res.json();
  const {employees: emps, months, month_labels} = data;

  // Filter to selected month
  const mKey = month.substring(0, 7); // "2026-01"
  const mIdx = months.indexOf(mKey);

  const activeEmps = emps.filter(e => (e.monthly_acv_eur[mKey] || 0) > 0 || true);

  // KPIs
  const totalAcv = activeEmps.reduce((s,e) => s + (e.monthly_acv_eur[mKey]||0), 0);
  const totalAcvMy = activeEmps.reduce((s,e) => s + (e.monthly_acv_my_eur[mKey]||0), 0);
  const withDeals = activeEmps.filter(e => (e.monthly_acv_eur[mKey]||0) > 0).length;
  document.getElementById('ae-mo-kpis').innerHTML =
    kpiCard('1st-year ACV', '\u20ac' + fmtNum(totalAcv), fmtMonth(month)) +
    kpiCard('Multi-year ACV', '\u20ac' + fmtNum(totalAcvMy), 'Incremental TCV') +
    kpiCard('AEs with Deals', withDeals, fmtMonth(month));

  // Bar chart
  const labels = activeEmps.map(e => e.name.split(' ')[0]);
  renderBar('ae-chart-mo', labels, activeEmps.map(e => e.monthly_acv_eur[mKey]||0), '1st-yr ACV (EUR)');

  // Table
  const heads = ['Name', 'Region', 'Cur', '1st-yr ACV (EUR)', 'Multi-yr ACV (EUR)', 'Total ACV (EUR)', 'Gate Status'];
  const rows = activeEmps.map(e => {
    const acv   = e.monthly_acv_eur[mKey]  || 0;
    const acvMy = e.monthly_acv_my_eur[mKey] || 0;
    // Gate check: ACV this month vs monthly portion of quarterly target (q_target / 3)
    // We show gate vs quarterly target on the quarterly tab; here just show raw ACV
    return [
      e.name, e.region, e.currency,
      '\u20ac' + fmtNum(acv),
      acvMy > 0 ? '\u20ac' + fmtNum(acvMy) : '\u2014',
      '<strong>\u20ac' + fmtNum(acv + acvMy) + '</strong>',
      acv > 0 ? '<span style="color:var(--green)">Active</span>' : '<span style="color:var(--dim)">\u2014</span>',
    ];
  });
  renderTable('ae-mo-table', heads, rows);
}

// ============================================================
// AE Quarterly Performance
// ============================================================
async function loadAEQuarterly() {
  const yr = document.getElementById('ae-q-year').value;
  const qt = parseInt(document.getElementById('ae-q-quarter').value);
  const res = await fetch('/api/ae_overview?year=' + yr);
  const data = await res.json();
  const {employees: emps} = data;

  const qAcvKey  = 'q' + qt + '_acv';
  const qGateKey = 'q' + qt + '_gate';

  const totalAcv  = emps.reduce((s,e) => s + (e[qAcvKey]||0), 0);
  const gatesMet  = emps.filter(e => e[qGateKey]).length;
  const avgAtt    = emps.length ? (emps.reduce((s,e) => {
    const t = (e.annual_target_eur||0) / 4;
    return s + (t > 0 ? (e[qAcvKey]||0) / t * 100 : 0);
  }, 0) / emps.length) : 0;

  document.getElementById('ae-q-kpis').innerHTML =
    kpiCard('Q' + qt + ' Total ACV', '\u20ac' + fmtNum(totalAcv), 'FY' + yr) +
    kpiCard('Gates Met', gatesMet + ' / ' + emps.length, '\u2265 50% of quarterly target') +
    kpiCard('Avg Attainment', avgAtt.toFixed(1) + '%', 'vs quarterly target');

  // Progress bars
  const prog = document.getElementById('ae-q-progress');
  prog.innerHTML = emps.map(e => {
    const qTarget = (e.annual_target_eur || 0) / 4;
    const acv     = e[qAcvKey] || 0;
    const pct     = qTarget > 0 ? Math.min(150, (acv / qTarget) * 100) : 0;
    const gateMet = e[qGateKey];
    const barCol  = gateMet ? 'var(--green)' : pct >= 30 ? 'var(--accent)' : 'var(--red)';
    return '<div style="margin-bottom:14px">' +
      '<div style="display:flex;justify-content:space-between;margin-bottom:4px">' +
        '<span style="font-size:13px;font-weight:600">' + e.name + '</span>' +
        '<span style="font-size:12px;color:var(--dim)">\u20ac' + fmtNum(acv) + ' / \u20ac' + fmtNum(qTarget) +
          (gateMet ? ' <span style="color:var(--green);font-weight:700">\u2713 Gate Met</span>' : ' <span style="color:var(--red);font-weight:600">\u2717 Gate Not Met</span>') +
        '</span>' +
      '</div>' +
      '<div style="background:var(--border);border-radius:10px;height:14px;position:relative">' +
        '<div style="background:' + barCol + ';width:' + Math.min(100,pct) + '%;height:14px;border-radius:10px"></div>' +
        '<div style="position:absolute;top:0;left:50%;height:14px;width:2px;background:var(--dim);opacity:.5"></div>' +
      '</div>' +
    '</div>';
  }).join('');

  // Table
  const heads = ['Name', 'Region', 'Cur', 'Q' + qt + ' ACV (EUR)', 'Q Target (EUR)', 'Attainment', 'Gate'];
  const rows = emps.map(e => {
    const qTarget = (e.annual_target_eur || 0) / 4;
    const acv     = e[qAcvKey] || 0;
    const att     = qTarget > 0 ? (acv / qTarget * 100).toFixed(1) : '0.0';
    const attColor = parseFloat(att) >= 100 ? 'var(--green)' : parseFloat(att) >= 50 ? 'var(--orange)' : 'var(--red)';
    return [
      e.name, e.region, e.currency,
      '\u20ac' + fmtNum(acv),
      '\u20ac' + fmtNum(qTarget),
      '<span style="color:' + attColor + ';font-weight:600">' + att + '%</span>',
      gateIcon(e[qGateKey]),
    ];
  });
  renderTable('ae-q-table', heads, rows);
}

// ============================================================
// Helpers
// ============================================================
function gateIcon(met) {
  return met
    ? '<span style="color:var(--green);font-weight:700">\u2713</span>'
    : '<span style="color:var(--red);font-weight:700">\u2717</span>';
}

"""


def build_html(role: str = "ae") -> str:
    return assemble_html(
        role=role,
        title="Commission Calculator — Normative (AE)",
        nav_links=_NAV_LINKS,
        role_tabs_html=_TABS_HTML,
        role_js=_ROLE_JS,
    )
