"""Dashboard CSS — shared across all role dashboards."""

CSS = """
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
