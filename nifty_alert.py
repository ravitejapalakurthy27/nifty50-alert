# Nifty Index Funds Drop Alert
# Monitors: Nifty 50, Nifty Next 50, Nifty Midcap 150, Nifty Smallcap 250
# Sends a single email when any index drops below its threshold vs previous close

import yfinance as yf
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

# Nifty Index Funds: (Yahoo Finance ticker, display name, drop threshold %)
INDICES = [
    ("^NSEI",              "Nifty 50",           -1.0),
    ("^NSMIDCP",           "Nifty Next 50",      -1.5),
    ("NIFTYMIDCAP150.NS",  "Nifty Midcap 150",   -1.5),
    ("NIFTYSMLCAP250.NS",  "Nifty Smallcap 250", -1.5),
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

# ── 3. Check each index ───────────────────────────────────────────────────────
triggered = []

for ticker_sym, name, threshold in INDICES:

    if state.get(ticker_sym, {}).get("last_alert_date") == today_str:
        print(f"  {name}: alert already sent today -- skipping.")
        continue

    try:
        t    = yf.Ticker(ticker_sym)
        # Fetch daily history — try ticker.history() first, fall back to yf.download()
        hist = t.history(period="1mo", interval="1d")
        if len(hist) < 2:
            dl = yf.download(ticker_sym, period="1mo", interval="1d",
                             auto_adjust=True, progress=False)
            if hasattr(dl.columns, 'levels'):
                dl.columns = [c[0] for c in dl.columns]
            hist = dl

        if len(hist) < 2:
            print(f"  WARNING: Not enough history for {name} ({ticker_sym}) -- skipping.")
            continue

        prev_close = float(hist["Close"].iloc[-2])
        if prev_close == 0:
            continue

        try:
            intra = t.history(period="1d", interval="1m")
            current_price = float(intra["Close"].iloc[-1]) if not intra.empty else float(hist["Close"].iloc[-1])
        except Exception:
            current_price = float(hist["Close"].iloc[-1])

        pct_change = ((current_price - prev_close) / prev_close) * 100.0
        direction  = "DOWN" if pct_change < 0 else "UP"

        print(f"  {name} ({ticker_sym}): Prev {prev_close:,.2f} | Current {current_price:,.2f} | {direction} {abs(pct_change):.2f}% (threshold {threshold}%)")

        if pct_change <= threshold:
            triggered.append({
                "ticker":        ticker_sym,
                "name":          name,
                "threshold":     threshold,
                "prev_close":    prev_close,
                "current_price": current_price,
                "pct_change":    pct_change,
            })

    except Exception as e:
        print(f"  ERROR fetching {name} ({ticker_sym}): {e}")

# ── 4. Send alert email ───────────────────────────────────────────────────────
if triggered:

    rows = ""
    for a in triggered:
        rows += f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;font-weight:600">{a['name']}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;color:#555">{a['prev_close']:,.2f}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;color:#555">{a['current_price']:,.2f}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;color:#c0392b;font-weight:700">{a['pct_change']:.2f}%</td>
          <td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;color:#888">{a['threshold']}%</td>
        </tr>"""

    html_body = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif">
  <div style="max-width:600px;margin:32px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.1)">

    <div style="background:#c0392b;padding:20px 28px">
      <p style="margin:0;color:#fff;font-size:13px;opacity:0.85">NSE India</p>
      <h1 style="margin:4px 0 0;color:#fff;font-size:22px;font-weight:700">Nifty Index Funds Alert</h1>
      <p style="margin:6px 0 0;color:#fff;font-size:13px;opacity:0.85">{now.strftime('%d %b %Y, %H:%M IST')}</p>
    </div>

    <div style="padding:24px 28px 8px">
      <p style="margin:0 0 16px;color:#333;font-size:14px">
        The following index funds have dropped beyond their alert thresholds:
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px">
        <thead>
          <tr style="background:#f9f9f9">
            <th style="padding:10px 14px;text-align:left;color:#666;font-weight:600;border-bottom:2px solid #eee">Index</th>
            <th style="padding:10px 14px;text-align:left;color:#666;font-weight:600;border-bottom:2px solid #eee">Prev Close</th>
            <th style="padding:10px 14px;text-align:left;color:#666;font-weight:600;border-bottom:2px solid #eee">Current</th>
            <th style="padding:10px 14px;text-align:left;color:#666;font-weight:600;border-bottom:2px solid #eee">Change</th>
            <th style="padding:10px 14px;text-align:left;color:#666;font-weight:600;border-bottom:2px solid #eee">Threshold</th>
          </tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>
    </div>

    <div style="padding:16px 28px 24px">
      <p style="margin:0;font-size:12px;color:#aaa">
        Prices from Yahoo Finance · may be ~15 min delayed · one alert per index per trading day
      </p>
    </div>

  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Nifty Index Funds Alert"
    msg["From"]    = GMAIL_USER
    msg["To"]      = RECIPIENT
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    names_str = ", ".join(a["name"] for a in triggered)
    print(f"Alert email sent for: {names_str}")

    for a in triggered:
        state[a["ticker"]] = {
            "last_alert_date": today_str,
            "alert_time_ist":  now.isoformat(),
            "prev_close":      a["prev_close"],
            "alert_price":     a["current_price"],
            "pct_change":      a["pct_change"],
        }

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

else:
    print(f"[{now.strftime('%H:%M IST')}] No alerts -- all indices above their thresholds.")
