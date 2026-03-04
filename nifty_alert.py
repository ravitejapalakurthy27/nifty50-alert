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

# Each entry: (yahoo_ticker, display_name, alert_threshold_pct)
INDICES = [
    ("^NSEI",       "Nifty 50",           -1.0),
    ("^NIFNXT50",   "Nifty Next 50",      -1.5),
    ("^NIFMDCP150", "Nifty Midcap 150",   -1.5),
    ("^NIFSMCP250", "Nifty Smallcap 250", -1.5),
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
        print(f"[{now.strftime('%H:%M IST')}] {name}: alert already sent today -- skipping.")
        continue

    try:
        t = yf.Ticker(ticker_sym)
        hist = t.history(period="7d", interval="1d")

        if len(hist) < 2:
            print(f"WARNING: Not enough history for {name} ({ticker_sym}) -- skipping.")
            continue

        prev_close = float(hist["Close"].iloc[-2])
        if prev_close == 0:
            print(f"WARNING: Zero prev_close for {name} -- skipping.")
            continue

        try:
            intra = t.history(period="1d", interval="1m")
            current_price = float(intra["Close"].iloc[-1]) if not intra.empty else float(hist["Close"].iloc[-1])
        except Exception:
            current_price = float(hist["Close"].iloc[-1])

        pct_change = ((current_price - prev_close) / prev_close) * 100.0
        direction  = "DOWN" if pct_change < 0 else "UP"

        print(
            f"[{now.strftime('%H:%M IST')}] {name} -- "
            f"Prev: {prev_close:,.2f} | Current: {current_price:,.2f} | "
            f"{direction} {abs(pct_change):.2f}% (threshold {threshold}%)"
        )

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
        print(f"ERROR fetching {name} ({ticker_sym}): {e}")

# ── 4. Send one combined alert email (if any index triggered) ─────────────────
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
            f"<td style='padding:9px;border:1px solid #ddd;color:#d32f2f'><b>{a['pct_change']:.2f}%</b></td>"
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

    print(f"Alert email sent for: {names_str}")

    # Persist state for each triggered index
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
