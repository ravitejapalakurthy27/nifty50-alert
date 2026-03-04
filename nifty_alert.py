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
THRESHOLD_PCT      = -1.0
STATE_FILE         = "alert_state.json"

# ── 1. Trading-hours gate (IST) ───────────────────────────────────────────────
IST = pytz.timezone("Asia/Kolkata")
now = datetime.now(IST)

market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

if not (market_open <= now <= market_close):
    print(f"[{now.strftime('%Y-%m-%d %H:%M IST')}] Outside trading hours -- skipping.")
    sys.exit(0)

# ── 2. Duplicate-alert guard ──────────────────────────────────────────────────
today_str = date.today().isoformat()

if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r") as f:
        state = json.load(f)
    if state.get("last_alert_date") == today_str:
        print(f"[{now.strftime('%H:%M IST')}] Alert already sent for {today_str} -- skipping.")
        sys.exit(0)

# ── 3. Fetch Nifty 50 data ────────────────────────────────────────────────────
print(f"[{now.strftime('%H:%M IST')}] Fetching Nifty 50 data...")
ticker = yf.Ticker("^NSEI")

hist = ticker.history(period="7d", interval="1d")
if len(hist) < 2:
    print("ERROR: Not enough historical data. Exiting.")
    sys.exit(1)

prev_close = float(hist["Close"].iloc[-2])

try:
    intra = ticker.history(period="1d", interval="1m")
    current_price = float(intra["Close"].iloc[-1]) if not intra.empty else float(hist["Close"].iloc[-1])
except Exception:
    current_price = float(hist["Close"].iloc[-1])

pct_change = ((current_price - prev_close) / prev_close) * 100.0
direction  = "DOWN" if pct_change < 0 else "UP"

print(
    f"[{now.strftime('%H:%M IST')}] Nifty 50 -- "
    f"Prev Close: {prev_close:,.2f}  |  Current: {current_price:,.2f}  |  "
    f"Change: {direction} {abs(pct_change):.2f}%"
)

# ── 4. Send alert if threshold crossed ───────────────────────────────────────
if pct_change <= THRESHOLD_PCT:
    color   = "#d32f2f"
    subject = f"Nifty 50 Alert: {pct_change:.2f}% drop today ({now.strftime('%d %b %Y')})"

    html_body = (
        "<html><body style='font-family:Arial,sans-serif;max-width:520px;margin:auto'>"
        f"<h2 style='color:{color}'>Nifty 50 Drop Alert</h2>"
        f"<p>The Nifty 50 index has fallen by "
        f"<strong style='color:{color}'>{pct_change:.2f}%</strong> from yesterday's close.</p>"
        "<table style='border-collapse:collapse;width:100%'>"
        "<tr style='background:#f5f5f5'>"
        "<td style='padding:8px;border:1px solid #ddd'><b>Previous Close</b></td>"
        f"<td style='padding:8px;border:1px solid #ddd'>{prev_close:,.2f}</td></tr>"
        "<tr><td style='padding:8px;border:1px solid #ddd'><b>Current Price</b></td>"
        f"<td style='padding:8px;border:1px solid #ddd'>{current_price:,.2f}</td></tr>"
        "<tr style='background:#fff3f3'>"
        "<td style='padding:8px;border:1px solid #ddd'><b>Change</b></td>"
        f"<td style='padding:8px;border:1px solid #ddd;color:{color}'><b>{pct_change:.2f}%</b></td></tr>"
        "<tr><td style='padding:8px;border:1px solid #ddd'><b>Alert Time</b></td>"
        f"<td style='padding:8px;border:1px solid #ddd'>{now.strftime('%d %b %Y, %H:%M IST')}</td></tr>"
        "</table>"
        "<p style='color:#777;font-size:12px;margin-top:20px'>"
        "Automated alert. Prices sourced from Yahoo Finance (may be ~15 min delayed).</p>"
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

    print(f"Alert email sent to {RECIPIENT}!")

    with open(STATE_FILE, "w") as f:
        json.dump({
            "last_alert_date": today_str,
            "alert_time_ist":  now.isoformat(),
            "prev_close":      prev_close,
            "alert_price":     current_price,
            "pct_change":      pct_change
        }, f, indent=2)
else:
    print(f"No alert needed -- change {pct_change:.2f}% is above threshold {THRESHOLD_PCT}%.")
