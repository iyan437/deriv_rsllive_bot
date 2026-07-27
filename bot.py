"""
ADVANCED HYBRID DERIV DIGIT BOT V2.1 - SERVER EDITION
Runs 24/7 on VPS/Replit. Email alerts only. No Pydroid dependencies.
"""

import asyncio
import websockets
import json
import smtplib
from email.message import EmailMessage
import ssl
from datetime import datetime
import pytz
import os
import sys

try:
    from config import DERIV_TOKEN, EMAIL_USER, EMAIL_PASS, TO_EMAIL, SYMBOL
except ModuleNotFoundError:
    print("❌ ERROR: config.py not found. Copy config.py.example to config.py and fill your keys.")
    sys.exit(1)

# ========== ADVANCED SETTINGS ==========
APP_ID = '1089'
SCAN_TICKS = 50
THRESHOLD_RARE = 8 
THRESHOLD_COMMON = 15

TRADE_DURATION = 5
MAX_LOSS_STREAK = 2
PAUSE_TICKS = 20
TREND_LOOKBACK = 5
TRADE_HOURS_START = 8 # 08:00 GMT
TRADE_HOURS_END = 22 # 22:00 GMT
# =======================================

digit_counts = [0]*10
ticks = []
prices = []
last_signal = ""
last_signal_tick = 0
tick_counter = 0
loss_streak = 0
in_pause = False
pause_counter = 0

ssl_context = ssl.create_default_context()
gmt = pytz.timezone('GMT')

def log(msg):
    print(f"[{datetime.now(gmt).strftime('%H:%M:%S')}] {msg}")

async def send_email(subject, body, alert_type="INFO"):
    emoji = {"SIGNAL":"📊", "WARNING":"⚠️", "PAUSE":"⏸️", "INFO":"✅"}.get(alert_type, "ℹ️")
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = f"{emoji} DerivBot: {subject}"
    msg['From'] = EMAIL_USER
    msg['To'] = TO_EMAIL
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
        log(f"Email Sent: {subject}")
    except Exception as e:
        log(f"Email error: {e}")

def check_time_filter():
    now = datetime.now(gmt).hour
    return TRADE_HOURS_START <= now < TRADE_HOURS_END

def check_trend():
    if len(prices) < TREND_LOOKBACK + 1:
        return None
    return "UP" if prices[-1] > prices[-TREND_LOOKBACK - 1] else "DOWN"

def get_best_digit():
    rarest_digit = digit_counts.index(min(digit_counts))
    common_digit = digit_counts.index(max(digit_counts))
    return rarest_digit, common_digit

async def hybrid_trade_logic(price):
    global digit_counts, ticks, prices, last_signal, last_signal_tick, tick_counter
    global loss_streak, in_pause, pause_counter

    tick_counter += 1
    last_digit = int(str(price)[-1])
    ticks.append(last_digit)
    prices.append(price)
    
    if len(ticks) > SCAN_TICKS:
        removed = ticks.pop(0)
        digit_counts[removed] -= 1
    if len(prices) > SCAN_TICKS:
        prices.pop(0)
    digit_counts[last_digit] += 1
    
    # PAUSE MANAGER
    if in_pause:
        pause_counter += 1
        if pause_counter % 5 == 0: # log every 5 ticks
            log(f"PAUSED: {pause_counter}/{PAUSE_TICKS}")
        if pause_counter >= PAUSE_TICKS:
            in_pause = False
            pause_counter = 0
            loss_streak = 0
            await send_email("Risk Pause Ended", "Bot has resumed scanning.", "INFO")
        return

    if len(ticks) < SCAN_TICKS:
        if tick_counter % 10 == 0: # log every 10 ticks
            log(f"Scanning... {len(ticks)}/{SCAN_TICKS}")
        return
    
    # HYBRID LOGIC
    time_ok = check_time_filter()
    trend = check_trend()
    cooldown_ok = (tick_counter - last_signal_tick) >= TRADE_DURATION
    risk_ok = loss_streak < MAX_LOSS_STREAK
    rarest, common = get_best_digit()
    
    # AUTO SWITCHER
    signal_type = None
    target_digit = None
    if digit_counts[rarest] <= THRESHOLD_RARE:
        signal_type = "MATCHES"
        target_digit = rarest
    elif digit_counts[common] >= THRESHOLD_COMMON:
        signal_type = "DIFFERS"
        target_digit = common
    
    can_send = signal_type and trend and time_ok and cooldown_ok and risk_ok
    
    if can_send and last_signal!= f"{signal_type}_{target_digit}":
        subject = f"SIGNAL: {signal_type} {target_digit}"
        body = f"""Deriv Hybrid Bot Alert

Symbol: {SYMBOL}
Time GMT: {datetime.now(gmt).strftime('%Y-%m-%d %H:%M:%S')}
Strategy: Auto-Switcher + Trend + Time Filter
Signal: Trade 'Digit {signal_type} {target_digit}'
Reason: 
- Rarest digit: {rarest} appeared {digit_counts[rarest]}/{SCAN_TICKS} times
- Most common: {common} appeared {digit_counts[common]}/{SCAN_TICKS} times 
- Trend: {trend}
- Last Price: {price}

Duration: {TRADE_DURATION} ticks
Loss Streak: {loss_streak}

Trade on: https://app.deriv.com/trade
"""
        await send_email(subject, body, "SIGNAL")
        log(f"SIGNAL SENT: {subject}")
        last_signal = f"{signal_type}_{target_digit}"
        last_signal_tick = tick_counter
    
    elif not time_ok:
        log("Outside trading hours. Waiting...")
    else:
        if tick_counter % 20 == 0:
            log(f"Tick:{last_digit} | R:{rarest}={digit_counts[rarest]} | C:{common}={digit_counts[common]} | Trend:{trend}")


async def main():
    uri = f"wss://ws.binaryws.com/websockets/v3?app_id={APP_ID}"
    await send_email("Bot Online", f"Advanced Hybrid Bot started on {SYMBOL}", "INFO")
    log("Bot started. Connecting to Deriv...")

    while True:
        try:
            async with websockets.connect(uri, ssl=ssl_context, ping_interval=20) as ws:
                await ws.send(json.dumps({"authorize": DERIV_TOKEN}))
                auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                
                if 'error' in auth_res:
                    await send_email("AUTH FAILED", auth_res['error']['message'], "WARNING")
                    log(f"AUTH FAILED: {auth_res['error']['message']}")
                    await asyncio.sleep(10)
                    continue

                log(f"Authenticated: {auth_res['authorize']['email']}")
                await ws.send(json.dumps({"ticks": SYMBOL, "subscribe": 1}))
                log(f"Subscribed to {SYMBOL}. Starting scan...")

                while True:
                    data = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
                    if 'tick' in data:
                        await hybrid_trade_logic(data['tick']['quote'])

        except Exception as e:
            await send_email("BOT ERROR", str(e), "WARNING")
            log(f"ERROR: {e}")
        log("Reconnecting in 10s...")
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
