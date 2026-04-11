"""Shared JavaScript injected into every role dashboard.

Role-specific modules must define:
  onRoleInit()  — called after months/employees load; sets up role-specific UI
  loadTab(name) — called by showTab(); dispatches to role-specific loaders
"""

SHARED_JS = """
// ============================================================
// State
// ============================================================
let months = [], employees = [], orgNodes = [], activeTab = '', charts = {};
let dvData = [], dvHeaders = [];

// ============================================================
// Init
// ============================================================
async function init() {
  const [mRes, eRes, oRes] = await Promise.all([fetch('/api/months'), fetch('/api/employees'), fetch('/api/org_chart')]);
  months = await mRes.json();
  employees = await eRes.json();
  orgNodes = await oRes.json();

  // Populate global month selector
  const gmEl = document.getElementById('global-month');
  months.slice().reverse().forEach(m => {
    const opt = document.createElement('option');
    opt.value = m; opt.text = fmtMonth(m);
    gmEl.appendChild(opt);
  });

  // Default to previous calendar month (fall back to most recent if not in data)
  const now = new Date();
  const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const prevStr = prev.getFullYear() + '-' + String(prev.getMonth() + 1).padStart(2, '0') + '-01';
  if ([...gmEl.options].some(o => o.value === prevStr)) gmEl.value = prevStr;

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
  if (!role) return arr;
  // sdr_lead shown alongside sdrs; am_lead shown alongside ams
  const group = role === 'sdr' ? ['sdr', 'sdr_lead']
              : role === 'am'  ? ['am',  'am_lead']
              : [role];
  return arr.filter(e => group.includes(e.role));
}

// ============================================================
// Org chart helpers
// ============================================================

// Returns a Set of all employee_ids that report (directly or transitively)
// to managerId, based on the full orgNodes list from /api/org_chart.
function getDescendants(managerId) {
  const result = new Set();
  const queue = [managerId];
  while (queue.length) {
    const id = queue.shift();
    orgNodes.forEach(n => {
      if ((n.manager_id || '') === id && !result.has(n.employee_id)) {
        result.add(n.employee_id);
        queue.push(n.employee_id);
      }
    });
  }
  return result;
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
  _wkUpdateQuarterControls();
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
function _wkUpdateQuarterControls() {
  const isAe = globalRole() === 'ae';
  const ctrl = document.getElementById('wk-quarter-controls');
  if (ctrl) ctrl.style.display = isAe ? '' : 'none';

  if (isAe) {
    // Populate year selector from available months if not already done
    const yrEl = document.getElementById('wk-year');
    if (yrEl && yrEl.options.length === 0) {
      const years = [...new Set(months.map(m => m.slice(0,4)))].sort();
      years.forEach(y => {
        const opt = document.createElement('option');
        opt.value = y; opt.text = y;
        yrEl.appendChild(opt);
      });
      // Default to latest year
      if (years.length) yrEl.value = years[years.length - 1];
    }
    // Default quarter to current calendar quarter
    const qEl = document.getElementById('wk-quarter');
    if (qEl && qEl.value === '') {
      const now = new Date();
      qEl.value = Math.ceil((now.getMonth() + 1) / 3);
    }
  }
}

async function loadWorkings() {
  const empId = document.getElementById('wk-emp').value;
  const month = document.getElementById('global-month').value;
  if (!empId) return;

  const isAe = globalRole() === 'ae';
  _wkUpdateQuarterControls();

  let url;
  let displayPeriod;
  if (isAe) {
    const year    = document.getElementById('wk-year')?.value;
    const quarter = document.getElementById('wk-quarter')?.value;
    if (!year || !quarter) return;
    url = '/api/commission_workings?employee_id=' + empId + '&year=' + year + '&quarter=' + quarter;
    const qLabels = {1:'Q1 (Jan\u2013Mar)',2:'Q2 (Apr\u2013Jun)',3:'Q3 (Jul\u2013Sep)',4:'Q4 (Oct\u2013Dec)'};
    displayPeriod = 'Q' + quarter + ' ' + year;
  } else {
    if (!month) return;
    url = '/api/commission_workings?employee_id=' + empId + '&month=' + month;
    displayPeriod = fmtMonth(month);
  }

  const res  = await fetch(url);
  const data = await res.json();
  const {rows, summary} = data;
  const cur = summary.currency || 'EUR';

  // ---- CS / AM (shared NRR-based bonus workings renderer) ----
  if (['cs', 'cs_lead', 'am', 'am_lead'].includes(globalRole())) {
    const isAm = ['am', 'am_lead'].includes(globalRole());
    const kpiEl = document.getElementById('wk-kpis');
    const refComm = (summary.referral_sao_comm||0) + (summary.referral_cw_comm||0);
    if (isAm) {
      kpiEl.innerHTML =
        kpiCard('Total Payout', fmtAmt(summary.total_commission||0, cur), fmtMonth(month)) +
        kpiCard('NRR Bonus (100%)', fmtAmt(summary.nrr_bonus||0, cur), 'NRR ' + (summary.nrr_pct ? summary.nrr_pct.toFixed(1) + '%' : '\u2014')) +
        kpiCard('Multi-year ACV', fmtAmt(summary.multi_year_comm||0, cur), '1% of year-2+ ACV') +
        kpiCard('Referral Comm', fmtAmt(refComm, cur), (summary.referral_sao_count||0) + ' referral' + ((summary.referral_sao_count||0) !== 1 ? 's' : '')) +
        ((summary.accelerator_topup||0) > 0 ? kpiCard('NRR Accelerator', fmtAmt(summary.accelerator_topup, cur), 'Q4 top-up') : '');
    } else {
      kpiEl.innerHTML =
        kpiCard('Total Payout', fmtAmt(summary.total_commission||0, cur), fmtMonth(month)) +
        kpiCard('NRR Bonus (50%)', fmtAmt(summary.nrr_bonus||0, cur), 'NRR ' + (summary.nrr_pct ? summary.nrr_pct.toFixed(1) + '%' : '\u2014')) +
        kpiCard('CSAT Bonus (35%)', fmtAmt(summary.csat_bonus||0, cur), 'CSAT ' + (summary.csat_score_pct ? summary.csat_score_pct.toFixed(1) + '%' : '\u2014')) +
        kpiCard('Credits Bonus (15%)', fmtAmt(summary.credits_bonus||0, cur), 'Credits ' + (summary.credits_used_pct ? summary.credits_used_pct.toFixed(1) + '%' : '\u2014')) +
        kpiCard('Referral Comm', fmtAmt(refComm, cur), (summary.referral_sao_count||0) + ' referral' + ((summary.referral_sao_count||0) !== 1 ? 's' : '')) +
        ((summary.accelerator_topup||0) > 0 ? kpiCard('NRR Accelerator', fmtAmt(summary.accelerator_topup, cur), 'Top-up') : '');
    }

    // Map quarterly bonus amounts from summary (backend returns commission:null for these rows)
    const bonusAmts = isAm ? {
      'AM Bonus \u2014 NRR (100%)': summary.nrr_bonus || 0,
    } : {
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
        const amt = r.commission != null ? '\u20ac' + fmtNum(r.commission) : '\u2014';
        tblHtml += '<tr style="background:#F9FAFB">';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim)"></td>';
        tblHtml += '<td style="padding:5px 12px;font-size:10px;color:var(--dim)">Base BoB</td>';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim)">' + (r.opportunity_name || '') + '</td>';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim);font-size:11px">' + rateDesc + '</td>';
        tblHtml += '<td style="padding:5px 12px;text-align:right;font-weight:700">' + amt + '</td>';
        tblHtml += '</tr>';
      } else if (r.type === 'CS NRR Numerator') {
        const amt = r.commission != null ? '\u20ac' + fmtNum(r.commission) : '\u2014';
        tblHtml += '<tr style="background:#F9FAFB;border-bottom:2px solid var(--border)">';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim)"></td>';
        tblHtml += '<td style="padding:5px 12px;font-size:10px;color:var(--dim)">NRR Numerator</td>';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim)">' + (r.opportunity_name || '') + '</td>';
        tblHtml += '<td style="padding:5px 12px;color:var(--dim);font-size:11px">' + rateDesc + '</td>';
        tblHtml += '<td style="padding:5px 12px;text-align:right;font-weight:700">' + amt + '</td>';
        tblHtml += '</tr>';
      } else if (r.type === 'CS NRR Account') {
        const net = r.commission != null ? (r.commission >= 0 ? '+\u20ac' : '-\u20ac') + fmtNum(Math.abs(r.commission)) : '\u2014';
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
    const acc   = summary.accelerator || {};
    const invoicedRows = rows.filter(r => !r.is_forecast);
    const totalAcvFY   = rows.reduce((s,r) => s + (r.acv_eur||0), 0);
    const totalAcvMY   = rows.reduce((s,r) => s + (r.multi_year_acv_eur||0), 0);
    const totalBaseC   = invoicedRows.reduce((s,r) => s + (r.base_commission||0), 0);
    const totalMyC     = invoicedRows.reduce((s,r) => s + (r.my_commission||0), 0);
    const gateStr      = acc.gate_met != null ? (acc.gate_met ? '\u2713 Gate met' : '\u2717 Gate not met') : '';
    const attStr       = acc.q_attainment_pct != null ? acc.q_attainment_pct.toFixed(1) + '% attainment' : '';
    const accel1       = acc.accelerator_1 || 0;
    const accel2       = acc.accelerator_2 || 0;
    const totalTopup   = acc.accelerator_topup || (totalBaseC + totalMyC + accel1 + accel2);

    kpiEl.innerHTML =
      kpiCard('1st-year ACV (close date)', '\u20ac' + fmtNum(totalAcvFY), attStr || displayPeriod) +
      kpiCard('Multi-year ACV', '\u20ac' + fmtNum(totalAcvMY), 'Incremental TCV') +
      kpiCard('Gate', gateStr || '\u2014', acc.q_target_eur ? '\u20ac' + fmtNum(acc.q_target_eur) + ' quarterly target' : '') +
      kpiCard('Base Commission (10%)', fmtAmt(totalBaseC, cur), displayPeriod) +
      (totalMyC > 0 ? kpiCard('Multi-yr Commission (1%)', fmtAmt(totalMyC, cur), displayPeriod) : '') +
      (accel1 > 0 ? kpiCard('Accelerator Tier 1 (12%)', fmtAmt(accel1, cur), '100\u2013150% of target') : '') +
      (accel2 > 0 ? kpiCard('Accelerator Tier 2 (15%)', fmtAmt(accel2, cur), '>150% of target') : '') +
      (totalTopup > 0 ? kpiCard('Total Payout', fmtAmt(totalTopup, cur), displayPeriod) : '');

    const heads = ['Close Date','Opportunity','Doc #','Cadence','1st-yr ACV (EUR)','Multi-yr ACV (EUR)','FX','Base Comm (10%)','Multi-yr Comm (1%)','Total'];
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
        '<tr><td colspan="10" style="color:var(--dim);padding:12px">No deals closed in ' + displayPeriod + '. Commission is paid at quarter-end for qualifying quarters.</td></tr>';
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

  const heads = ['Date','Type','Opportunity','SAO Type','ACV (EUR)','FX','Rate / SDR','Commission'];
  const rowData = rows.map(r => {
    const isForecast   = r.is_forecast;
    const isSpif       = r.type === 'SPIF';
    const isSummary    = r.type === 'Team SAOs' || r.type === 'Team ACV';
    const commStr = r.commission !== null && r.commission !== undefined
      ? (isForecast
          ? '<span style="color:var(--dim)">' + fmtAmt(r.commission, cur) + ' (fcst)</span>'
          : isSpif
            ? '<strong style="color:var(--purple)">' + fmtAmt(r.commission, cur) + '</strong>'
            : '<strong>' + fmtAmt(r.commission, cur) + '</strong>')
      : '\u2014';
    const typeLabel = isSpif
      ? '<span style="color:var(--purple);font-weight:700">' + r.type + '</span>'
      : isSummary
        ? '<strong>' + r.type + '</strong>'
        : r.type;
    const oppLabel = isSummary
      ? '<strong>' + (r.opportunity_name || '') + '</strong>'
      : (r.opportunity_name || r.opportunity_id || '');
    return [
      r.date, typeLabel, oppLabel,
      r.sao_type ? r.sao_type.charAt(0).toUpperCase()+r.sao_type.slice(1) : '',
      r.acv_eur != null ? fmtAmt(r.acv_eur,'EUR') : '\u2014',
      r.fx_rate ? r.fx_rate.toFixed(4) : '\u2014',
      isSpif ? '' : r.rate_desc, commStr
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
    'sdr_q1_2026_8week': 'SDR Q1 2026 \u2014 Closed Won within 8 weeks of SAO',
    'ae_q1_2026_first_to_target': 'AE Q1 2026 \u2014 First to Target',
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
      ? '<span style="color:var(--dim)">\u2014 (no bonus)</span>'
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
