"""Machon Maane — live campaign dashboard.
Serves a dashboard that pulls fresh numbers from the Meta Marketing API on each
page load (with a short server-side cache), and emails a daily digest.
All secrets come from environment variables.
"""
import os, time, json, threading, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from flask import Flask, Response

V = "v23.0"
TOKEN   = os.environ["META_ACCESS_TOKEN"]
ACCT    = os.environ["META_AD_ACCOUNT_ID"]
CAMP    = os.environ["MAANE_CAMPAIGN_ID"]
BUDGET  = int(os.environ.get("VALIDATION_BUDGET", "1500"))
GOAL    = int(os.environ.get("LEAD_GOAL", "200"))
CACHE_TTL = int(os.environ.get("CACHE_TTL", "180"))          # seconds
JER = timezone(timedelta(hours=3))

RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
DIGEST_FROM = os.environ.get("DIGEST_FROM", "maane@barlevav.com")
DIGEST_TO   = os.environ.get("DIGEST_TO", "")
DIGEST_HOUR = int(os.environ.get("DIGEST_HOUR", "8"))
SHEET_URL   = os.environ.get("MAANE_LEADS_URL", "")
SHEET_TOKEN = os.environ.get("MAANE_LEADS_TOKEN", "")

app = Flask(__name__)

# ---------- Meta ----------
def meta_get(path, **params):
    params["access_token"] = TOKEN
    url = f"https://graph.facebook.com/{V}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=45) as r:
        return json.loads(r.read().decode())

LEAD_KEYS = ("offsite_conversion.fb_pixel_lead", "lead", "onsite_web_lead")
def leads_of(row):
    # Meta reports the same conversion under several "lead" labels; count ONE, not the sum.
    acts = {a.get("action_type"): float(a.get("value", 0)) for a in (row.get("actions") or [])}
    for k in LEAD_KEYS:
        if k in acts:
            return acts[k]
    return 0.0

def agg(rows):
    spend = sum(float(r.get("spend", 0)) for r in rows)
    impr  = sum(float(r.get("impressions", 0)) for r in rows)
    clicks= sum(float(r.get("clicks", 0)) for r in rows)
    leads = sum(leads_of(r) for r in rows)
    reach = sum(float(r.get("reach", 0)) for r in rows)
    return dict(spend=spend, impr=impr, clicks=clicks, leads=leads, reach=reach,
                ctr=(clicks/impr*100 if impr else 0), cpc=(spend/clicks if clicks else 0),
                cpl=(spend/leads if leads else 0))

def fetch_sheet():
    """Total leads (all sources) from the Google Sheet — display only, not used for cost math."""
    if not (SHEET_URL and SHEET_TOKEN):
        return None
    try:
        url = SHEET_URL + ("&" if "?" in SHEET_URL else "?") + urllib.parse.urlencode({"token": SHEET_TOKEN})
        with urllib.request.urlopen(url, timeout=20) as r:
            d = json.loads(r.read().decode())
        return d if d.get("ok") else None
    except Exception:
        return None

def fetch():
    try:
        rows = meta_get(f"{CAMP}/insights", level="ad", date_preset="maximum",
                        fields="spend,impressions,clicks,reach,actions,ad_name,adset_name").get("data", [])
        err = None
    except Exception as e:
        rows, err = [], str(e)[:200]
    return {"error": err, "ad_rows": rows, "sheet": fetch_sheet()}

# ---------- render ----------
def fnum(x, d=0):
    try: return f"{float(x):,.{d}f}"
    except: return "0"

CSS = """<style>
:root{--paper:#FAF6EF;--paper2:#F2EADB;--card:#FFF;--edge:#E7DCC8;--ink:#33291F;--ink2:#574B3C;--ink3:#8A7C68;--gold:#B08D4F;--goldd:#8A6D38;--goldw:#F6EEDD;--go:#5E7F63;--shadow:0 1px 2px rgba(51,41,31,.05),0 6px 20px rgba(51,41,31,.06);--rule:#E2D6BF}
@media (prefers-color-scheme:dark){:root{--paper:#211C17;--paper2:#282219;--card:#2D2720;--edge:#3D352A;--ink:#EFE6D4;--ink2:#C9BCA5;--ink3:#948872;--gold:#CBA869;--goldd:#B7924E;--goldw:#322A1F;--go:#8FB093;--rule:#3A3125;--shadow:0 1px 2px rgba(0,0,0,.25),0 8px 26px rgba(0,0,0,.3)}}
:root[data-theme=light]{--paper:#FAF6EF;--paper2:#F2EADB;--card:#FFF;--edge:#E7DCC8;--ink:#33291F;--ink2:#574B3C;--ink3:#8A7C68;--gold:#B08D4F;--goldd:#8A6D38;--goldw:#F6EEDD;--go:#5E7F63;--rule:#E2D6BF}
:root[data-theme=dark]{--paper:#211C17;--paper2:#282219;--card:#2D2720;--edge:#3D352A;--ink:#EFE6D4;--ink2:#C9BCA5;--ink3:#948872;--gold:#CBA869;--goldd:#B7924E;--goldw:#322A1F;--go:#8FB093;--rule:#3A3125}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Assistant",system-ui,"Segoe UI",Arial,sans-serif;line-height:1.6}
.wrap{max-width:1000px;margin:0 auto;padding:32px 22px 60px}
h1,h2{font-family:"Noto Serif Hebrew","Frank Ruhl Libre",Georgia,serif;font-weight:400;margin:0}
.eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--goldd);font-weight:600}
h1{font-size:30px;margin:6px 0 4px}.meta{color:var(--ink3);font-size:13px;margin-bottom:26px}
.status{display:inline-block;font-size:12px;font-weight:700;padding:2px 10px;border-radius:999px;background:rgba(94,127,99,.15);color:var(--go);margin-left:8px}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:26px}
.kpi{background:var(--card);border:1px solid var(--edge);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow)}
.klabel{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3)}
.kval{font-family:Georgia,serif;font-size:32px;color:var(--ink);font-variant-numeric:tabular-nums;margin:4px 0 2px}.ksub{font-size:12px;color:var(--ink3)}
.bars{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:26px}
.bar{background:var(--card);border:1px solid var(--edge);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow)}
.bar .t{font-size:13px;color:var(--ink2);margin-bottom:8px}
.track{height:12px;background:var(--paper2);border-radius:999px;overflow:hidden}.fill{height:100%;background:linear-gradient(90deg,var(--gold),var(--goldd))}.fill.go{background:linear-gradient(90deg,#7FA084,var(--go))}
h2{font-size:20px;margin:24px 0 12px}
.tablewrap{overflow-x:auto;border:1px solid var(--edge);border-radius:14px;box-shadow:var(--shadow)}
table{border-collapse:collapse;width:100%;min-width:560px;background:var(--card);font-size:14px}
th,td{padding:11px 14px;text-align:left;border-bottom:1px solid var(--rule);font-variant-numeric:tabular-nums}
th{background:var(--paper2);font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:var(--ink)}
td.he{direction:rtl;text-align:right;font-weight:600}tr:last-child td{border-bottom:none}
.empty{color:var(--ink3);text-align:center;font-style:italic}
.note{background:var(--goldw);border:1px solid var(--rule);border-left:3px solid var(--gold);border-radius:10px;padding:14px 16px;margin-top:22px;font-size:14px;color:var(--ink2)}.note b{color:var(--goldd)}
.foot{color:var(--ink3);font-size:12px;margin-top:26px}
@media(max-width:720px){.kpis{grid-template-columns:1fr 1fr}.bars{grid-template-columns:1fr}}
</style>"""

def row_cells(name, rows):
    a = agg(rows)
    return (f'<tr><td class="he">{name}</td><td>₪{fnum(a["spend"],0)}</td><td>{fnum(a["leads"],0)}</td>'
            f'<td>{"₪"+fnum(a["cpl"],0) if a["leads"] else "—"}</td><td>{fnum(a["impr"],0)}</td>'
            f'<td>{fnum(a["ctr"],2)}%</td></tr>')

def render(data):
    ad_rows = data["ad_rows"]
    tot = agg(ad_rows)
    updated = datetime.now(JER).strftime("%Y-%m-%d %H:%M")
    err = data.get("error")
    sheet = data.get("sheet")
    total_leads = sheet.get("total") if sheet else None
    registered  = sheet.get("registered") if sheet else None
    def kpi(l, v, s=""): return f'<div class="kpi"><div class="klabel">{l}</div><div class="kval">{v}</div><div class="ksub">{s}</div></div>'
    total_sub = "all sources" + (f" · {int(registered)} registered" if registered is not None else "")
    kpis = "".join([
        kpi("Spend", "₪"+fnum(tot["spend"],0), f'of ₪{BUDGET:,} budget'),
        kpi("Ad-attributed leads", fnum(tot["leads"],0), "matched to ads by Meta"),
        kpi("Total leads", (fnum(total_leads,0) if total_leads is not None else "—"), total_sub),
        kpi("Cost / Lead", ("₪"+fnum(tot["cpl"],0)) if tot["leads"] else "—", "per ad-attributed lead"),
        kpi("Impressions", fnum(tot["impr"],0), f'reach {fnum(tot["reach"],0)}'),
        kpi("Clicks", fnum(tot["clicks"],0), f'CTR {fnum(tot["ctr"],2)}% · CPC ₪{fnum(tot["cpc"],2)}'),
    ])
    groups = defaultdict(list)
    for r in ad_rows: groups[r.get("adset_name","?")].append(r)
    adset_html = "".join(row_cells(n, rs) for n, rs in groups.items()) or '<tr><td colspan="6" class="empty">No delivery yet — fills in shortly.</td></tr>'
    ad_html = "".join(row_cells(r.get("ad_name","?"), [r]) for r in ad_rows) or '<tr><td colspan="6" class="empty">No delivery yet.</td></tr>'
    leads_goal = total_leads if total_leads is not None else tot["leads"]
    pb = min(100, tot["spend"]/BUDGET*100) if BUDGET else 0
    pg = min(100, leads_goal/GOAL*100) if GOAL else 0
    errbanner = f'<div class="note"><b>Note:</b> couldn\'t reach Meta just now ({err}). Showing last good render; retry on reload.</div>' if err else ""
    return f"""<!doctype html><html lang="en"><head><title>Machon Maane — Campaign Dashboard</title>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="180">{CSS}</head><body><div class="wrap">
<p class="eyebrow">Live Campaign · Validation Round</p>
<h1>Machon Maane — Leads Dashboard<span class="status">● LIVE</span></h1>
<p class="meta">Facebook + Instagram · optimizing for form submissions · auto-refreshes every 3 min · updated {updated} (Israel time)</p>
{errbanner}
<div class="kpis">{kpis}</div>
<div class="bars">
<div class="bar"><div class="t">Budget spent · ₪{fnum(tot['spend'],0)} of ₪{BUDGET:,}</div><div class="track"><div class="fill" style="width:{pb:.1f}%"></div></div></div>
<div class="bar"><div class="t">Leads · {fnum(leads_goal,0)} of {GOAL} goal · all sources</div><div class="track"><div class="fill go" style="width:{pg:.1f}%"></div></div></div>
</div>
<h2>By audience</h2><div class="tablewrap"><table><thead><tr><th>Audience</th><th>Spend</th><th>Leads</th><th>Cost/Lead</th><th>Impr.</th><th>CTR</th></tr></thead><tbody>{adset_html}</tbody></table></div>
<h2>By ad (which creative wins)</h2><div class="tablewrap"><table><thead><tr><th>Ad</th><th>Spend</th><th>Leads</th><th>Cost/Lead</th><th>Impr.</th><th>CTR</th></tr></thead><tbody>{ad_html}</tbody></table></div>
<div class="note"><b>How to read this:</b> <b>Total leads</b> is every form submission — your real count, from the sheet. <b>Ad-attributed leads</b> is the subset Meta can trace back to an ad; it's normally lower, and it's what <b>Cost per Lead</b> is based on (the fair measure of ad performance). <b>Registered</b> = leads Aya marked as signed up for a class. Once each ad has enough leads we pause the weak ones and back the winner.</div>
<p class="foot">Live from the Meta Marketing API · Machon Maane campaign dashboard</p>
</div></body></html>"""

# ---------- cache ----------
_cache = {"t": 0, "html": "<h1>Loading…</h1>"}
_lock = threading.Lock()
def current_html():
    now = time.time()
    with _lock:
        if now - _cache["t"] > CACHE_TTL or _cache["t"] == 0:
            _cache["html"] = render(fetch()); _cache["t"] = now
        return _cache["html"]

@app.route("/")
def index():
    return Response(current_html(), mimetype="text/html")

@app.route("/healthz")
def healthz():
    return "ok"

# ---------- daily digest ----------
def send_digest():
    if not (RESEND_KEY and DIGEST_TO): return
    data = fetch(); tot = agg(data["ad_rows"])
    total_leads = (data.get("sheet") or {}).get("total")
    d = datetime.now(JER).strftime("%d/%m/%Y")
    cpl = ("₪"+fnum(tot["cpl"],0)) if tot["leads"] else "—"
    tl = fnum(total_leads,0) if total_leads is not None else "—"
    html = (f'<div style="font-family:Arial,sans-serif;color:#3A322A;max-width:520px">'
            f'<h2 style="color:#8A6D38;font-weight:normal">מכון מענה · סיכום קמפיין יומי</h2>'
            f'<p style="color:#8A7C68">{d}</p>'
            f'<table style="width:100%;border-collapse:collapse;font-size:15px">'
            f'<tr><td>הוצאה</td><td style="text-align:left"><b>₪{fnum(tot["spend"],0)}</b> מתוך ₪{BUDGET:,}</td></tr>'
            f'<tr><td>לידים (סה״כ)</td><td style="text-align:left"><b>{tl}</b> מתוך {GOAL}</td></tr>'
            f'<tr><td>מתוכם משויכים לפרסום</td><td style="text-align:left">{fnum(tot["leads"],0)}</td></tr>'
            f'<tr><td>עלות לליד (פרסום)</td><td style="text-align:left"><b>{cpl}</b></td></tr>'
            f'<tr><td>חשיפות</td><td style="text-align:left">{fnum(tot["impr"],0)} · CTR {fnum(tot["ctr"],2)}%</td></tr>'
            f'</table><p style="margin-top:18px"><a href="https://maane.barlevav.com" style="color:#B08D4F">לדשבורד המלא ←</a></p></div>')
    body = json.dumps({"from": DIGEST_FROM, "to": [DIGEST_TO],
                       "subject": f"מכון מענה · סיכום קמפיין {d}", "html": html}).encode()
    req = urllib.request.Request("https://api.resend.com/emails", data=body,
                                 headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass

def digest_loop():
    sent_on = None
    while True:
        now = datetime.now(JER)
        if now.hour == DIGEST_HOUR and now.date() != sent_on:
            send_digest(); sent_on = now.date()
        time.sleep(300)

if os.environ.get("ENABLE_DIGEST", "1") == "1":
    threading.Thread(target=digest_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
