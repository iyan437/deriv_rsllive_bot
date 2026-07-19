import os
import json
import asyncio
import websockets
import smtplib
from email.message import EmailMessage
import time

# Load secure credentials from GitHub Secrets
API_TOKEN = os.environ.get("DERIV_API_TOKEN")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# Configuration settings
SYMBOL = "1HZ100V"        # Volatility 100 (1s) Index (Fastest tick stream)
COOLDOWN_SECONDS = 300   # Strict 5-minute filter to avoid inbox spamming

# State management variables
last_signal_time = 0
consecutive_count = 0
previous_digit = None

def send_email_signal(subject, body):
    """Sends the alert email synchronously using a standard secure SSL connection."""
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_SENDER
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL('://gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print("⚡ Email signal successfully dispatched!")
    except Exception as e:
        print(f"❌ Mail delivery failed: {e}")

async def connect_deriv_stream():
    """Establishes a live persistent websocket connection with Deriv's API servers."""
    global last_signal_time, consecutive_count, previous_digit
    
    # Official Deriv API Websocket endpoint URL
    uri = "wss://://derivws.com" 
    
    print(f"Connecting to live market data stream for {SYMBOL}...")
    
    async with websockets.connect(uri) as websocket:
        # Step 1: Authenticate the session
        auth_request = {"authorize": API_TOKEN}
        await websocket.send(json.dumps(auth_request))
        auth_response = await websocket.recv()
        print("Session Authentication: Complete")

        # Step 2: Subscribe to real-time tick streaming data
        subscribe_request = {"ticks": SYMBOL}
        await websocket.send(json.dumps(subscribe_request))
        print(f"Live subscription active. Analyzing streaming ticks...")

        # Step 3: Listen to live ticks continuously as they stream in
        async for message in websocket:
            data = json.loads(message)
            
            if "tick" in data:
                current_price = str(data["tick"]["quote"])
                last_digit = int(current_price[-1]) # Extract the final digit
                
                # --- STRATEGY LOGIC: Match & Differ Alert ---
                # Example strategy: Identify when the same digit repeats consecutively
                if previous_digit is not None and last_digit == previous_digit:
                    consecutive_count += 1
                else:
                    consecutive_count = 1
                
                previous_digit = last_digit
                
                # Trigger criteria: Same digit repeats twice in a row
                if consecutive_count >= 2:
                    current_time = time.time()
                    elapsed_time = current_time - last_signal_time
                    
                    # Enforce the strict minimum 5-minute safety delay window
                    if elapsed_time >= COOLDOWN_SECONDS:
                        subject = f"🚨 Deriv Live Signal Alert: Digit [{last_digit}] Repeat"
                        body = (
                            f"Live Market Event Detected!\n\n"
                            f"Asset: {SYMBOL}\n"
                            f"Pattern: Digit {last_digit} repeated {consecutive_count} times in a row.\n"
                            f"Price Context: {current_price}\n\n"
                            f"Strategy Recommendation: Look for Matches/Differs setups."
                        )
                        
                        # Send instantly without blocking the active stream data
                        send_email_signal(subject, body)
                        last_signal_time = current_time
                    else:
                        remaining = int(COOLDOWN_SECONDS - elapsed_time)
                        print(f"Signal suppressed. Cooldown active for {remaining} more seconds.")

if __name__ == "__main__":
    try:
        asyncio.run(connect_deriv_stream())
    except KeyboardInterrupt:
        print("Bot session terminated by user.")
