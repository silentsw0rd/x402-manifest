import os
import json
from dotenv import load_dotenv
from x402_client import X402Client

load_dotenv()

# 1. Load private key from environment
private_key = os.getenv("AGENT_PRIVATE_KEY") or os.getenv("RELAYER_PRIVATE_KEY")

if not private_key:
    print("[!] Error: No private key found in .env (expected AGENT_PRIVATE_KEY or RELAYER_PRIVATE_KEY).")
    exit(1)

# 2. Target local running server.py
GATEWAY_URL = "http://localhost:8000"

print("=" * 50)
print(" Testing x402-client SDK Integration")
print("=" * 50)
print(f"Gateway URL: {GATEWAY_URL}")

# 3. Instantiate client
client = X402Client(private_key=private_key, gateway_url=GATEWAY_URL)
print(f"Client Wallet Address: {client.account.address}")

# 4. Define target extraction & dynamic schema
target_url = "https://news.ycombinator.com"
schema = {
    "top_title": "Title of the top story on the page",
    "top_points": "Number of points or upvotes"
}

print(f"\nSending extraction request for {target_url}...")

try:
    # SDK handles 402 challenge detection, EIP-712 signing, and retrying automatically
    result = client.extract(url=target_url, schema_spec=schema)
    
    print("\n[SUCCESS] Extraction completed!")
    print(json.dumps(result, indent=2))

except Exception as e:
    print(f"\n[FAIL] SDK request failed: {e}")