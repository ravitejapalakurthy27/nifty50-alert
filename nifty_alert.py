import requests
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
import pytz
import json
import os
import sys

# ── Config ────────────────────────────────────────────────────────────────────
GMAIL_USER         = "raviteja.palakurthy27@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECIPIENT          = "raviteja.palakurthy27@gmail.com"
STATE_FILE         = "alert_state.json"

# NSE index name (as returned by API) -> (display name, alert threshold %)
INDICES = [
    ("NIFTY 50",         "Nifty 50",           -1.0),
    ("NIFTY NEXT 50",    "Nifty Next 50",      -1.5),
    ("NIFTY MIDCAP 150", "Nifty Midcap 150",   -1.5),
    ("NIFTY SMLCAP 250", "Nifty Smallcap 250", -1.5),
]

# ── 1. Trading-hours gate (IST) ───────────────────────────────────────────────
IST = pytz.timezone("Asia/Kolkata")
now = datetime.now(IST)

market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

if not (market_open <= now <= market_close):
    print(f"[{now.strftime('%Y-%m-%d %H:%M IST')}] Outside trading hours -- skipping.")
    sys.exit(0)

# ── 2. Load persisted state ───────────────────────────────────────────────────
today_str = date.today().isoformat()
state = {}

if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r") as f:
        state = json.load(f)

# ── 3. Fetch all NSE index data from official NSE API ────────────────────────
def fetch_nse_indices():
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer":         "https://www.nseindia.com/",
    })
    # Establish session cookies by visiting homepage first
    session.get("https://www.nseindia.com/", timeout=15)
    time.sleep(2)
    resp = session.get("https://www.nseindia.com/api/allIndices", timeout=15)
    resp.raise_for_status()
    return {item["index"]: item for item in resp.json()["data"]}

print(f"[{now.strftime('%H:%M IST')}] Fetching NSE index data...")
try:
    index_map = fetch_nse_indices()
    print(f"[{now.strftime('%H:%M IST')}] Fetched data for {len(index_map)} indices.")
except Exception as e:
    print(f"ERROR: Could not fetch NSE data: {e}")
    sys.exit(1)

# ── 4. Check each index ───────────────────────────────────────────────────────
triggered = []

for nse_key, display_name, threshold in INDICES:

    if state.get(nse_key, {}).get("last_alert_date") == today_str:
        print(f"  {display_name}: alert already sent today -- skipping.")
        continue

    entry = index_map.get(nse_key)
    if not entry:
        print(f"  WARNING: '{nse_key}' not found in NSE response -- skipping.")
        continue

    current_price = float(entry["last"])
    prev_close    = float(entry["previousClose"])

    if prev_close == 0:
        print(f"  WARNING: zero previousClose for {display_name} -- skipping.")
        continue

    pct_change = float(entry.get("percentChange",
                       ((current_price - prev_close) / prev_close) * 100))
    direction  = "DOWN" if pct_change < 0 else "UP"

    print(
        f"  {display_name}: Prev {prev_close:,.2f} | "
        f"Current {current_price:,.2f} | {direction} {abs(pct_change):.2f}% "
        f"(threshold {threshold}%)"
    )

    if pct_change <= threshold:
        triggered.append({
            "key":           nse_key,
            "name":          display_name,
            "threshold":     threshold,
            "prev_close":    prev_close,
            "current_price": current_price,
            "pct_change":    pct_change,
        })

# ── 5. Send one combined alert email ─────────────────────────────────────────
if triggered:
    names_str = ", ".join(a["name"] for a in triggered)
    subject   = f"Index Drop Alert: {names_str} ({now.strftime('%d %b %Y, %H:%M IST')})"

    rows = ""
    for a in triggered:
        rows += (
            "<tr style='background:#fff3f3'>"
            f"<td style='padding:9px;border:1px solid #ddd'><b>{a['name']}</b></td>"
            f"<td style='padding:9px;border:1px solid #ddd'>{a['prev_close']:,.2f}</td>"
            f"<td style='padding:9px;border:1px solid #ddd'>{a['current_price']:,.2f}</td>"
            f"<td style='padding:9px;border:1px solid #ddd;color:#d32f2f'>"
            f"<b>{a['pct_change']:.2f}%</b></td>"
            f"<td style='padding:9px;border:1px solid #ddd'>at or below {a['threshold']}%</td>"
            "</tr>"
        )

    html_body = (
        "<html><body style='font-family:Arial,sans-serif;max-width:680px;margin:auto'>"
        "<h2 style='color:#d32f2f'>Index Drop Alert</h2>"
        f"<p>The following indices crossed their drop thresholds as of "
        f"<b>{now.strftime('%d %b %Y, %H:%M IST')}</b>:</p>"
        "<table style='border-collapse:collapse;width:100%'>"
        "<tr style='background:#333;color:white'>"
        "<th style='padding:9px;text-align:left'>Index</th>"
        "<th style='padding:9px;text-align:left'>Prev Close</th>"
        "<th style='padding:9px;text-align:left'>Current Price</th>"
        "<th style='padding:9px;text-align:left'>Change</th>"
        "<th style='padding:9px;text-align:left'>Threshold</th>"
        "</tr>"
        f"{rows}"
        "</table>"
        "<p style='color:#777;font-size:12px;margin-top:20px'>"
        "Automated alert. Data sourced from NSE India (real-time).</p>"
        "</body></html>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = RECIPIENT
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"Alert email sent for: {names_str}")

    for a in triggered:
        state[a["key"]] = {
            "last_alert_date": today_str,
            "alert_time_ist":  now.isoformat(),
            "prev_close":      a["prev_close"],
            "alert_price":     a["current_price"],
            "pct_change":      a["pct_change"],
        }

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

else:
    print(f"No alerts triggered -- all indices above their thresholds.")
