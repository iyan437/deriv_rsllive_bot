import os
import json
import asyncio
import websockets
import time
import urllib.request

# Load secure credentials from GitHub Secrets
API_TOKEN = os.environ.get("DERIV_API_TOKEN")

# PIPEDREAM CONFIGURATION: Paste your unique Pipedream Webhook URL here
PIPEDREAM_WEBHOOK_URL = "https://eou42nuld2hd1p1.m.pipedream.net"

# Strategy Settings
SYMBOL = "1HZ100V"        # Volatility 100 (1s) Index
COOLDOWN_SECONDS = 300   # 5-minute safety cooldown

# State management variables
last_signal_time = 0
consecutive_count = 0
previous_digit = None

def trigger_pipedream_alert(last_digit, count, price):
    """Sends the trigger payload to your Pipedream workflow endpoint using standard urllib."""
    payload = {
        "asset": SYMBOL,
        "pattern": f"Digit {last_digit} repeated {count} times in a row.",
        "price": price,
        "recommendation": "Look for Matches/Differs setups."
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        PIPEDREAM_WEBHOOK_URL, 
        data=data, 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200 or response.status == 201:
                print("🚀 Signal pushed to Pipedream successfully!")
    except Exception as e:
        print(f"❌ Failed to reach Pipedream: {e}")

async def connect_deriv_stream():
    """Establishes a live persistent websocket connection with Deriv's API servers."""
    global last_signal_time, consecutive_count, previous_digit
    
    uri = "wss://ws.derivws.com/websockets/v3" 
    print(f"Connecting to live market data stream for {SYMBOL}...")
    
    async with websockets.connect(uri) as websocket:
        # Step 1: Authenticate the session
        await websocket.send(json.dumps({"authorize": API_TOKEN}))
        auth_response = await websocket.recv()
        auth_data = json.loads(auth_response)
        
        if "error" in auth_data:
            print(f"❌ Authorization failed: {auth_data['error']['message']}")
            return
            
        print("Session Authentication: Complete")

        # Step 2: Subscribe to real-time tick streaming data
        await websocket.send(json.dumps({"ticks": SYMBOL}))
        print(f"Live subscription active. Analyzing streaming ticks...")

        # Step 3: Listen to live ticks continuously
        async for message in websocket:
            data = json.loads(message)
            
            if "tick" in data:
                current_price = str(data["tick"]["quote"])
                last_digit = int(current_price[-1]) 
                
                if previous_digit is not None and last_digit == previous_digit:
                    consecutive_count += 1
                else:
                    consecutive_count = 1
                
                previous_digit = last_digit
                
                if consecutive_count >= 2:
                    current_time = time.time()
                    elapsed_time = current_time - last_signal_time
                    
                    if elapsed_time >= COOLDOWN_SECONDS:
                        # Offload the HTTP request to Pipedream to keep websocket alive
                        print(f"🎯 Pattern Found! Digit {last_digit} repeated.")
                        asyncio.to_thread(trigger_pipedream_alert, last_digit, consecutive_count, current_price)
                        last_signal_time = current_time
                    else:
                        remaining = int(COOLDOWN_SECONDS - elapsed_time)
                        print(f"Signal suppressed. Cooldown active for {remaining} seconds.")
