import json
import base64
import time
import urllib.request
import urllib.error
from eth_account import Account
from eth_account.messages import encode_typed_data

print("=" * 50)
print(" Generating Zero-Balance Burner Wallet")
print("=" * 50)

# 1. Generate brand-new empty burner wallet (0 USDC balance)
burner = Account.create()
address = burner.address
key = burner.key.hex()

print(f"Burner Address: {address}")

# 2. Construct valid EIP-712 authorization envelope
domain = {
    "name": "USD Coin",
    "version": "2",
    "chainId": 8453,
    "verifyingContract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
}

types = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"}
    ],
    "ReceiveWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"}
    ]
}

message = {
    "from": address,
    "to": "0xd2eA78C3eeA0Ed3275b2465915527eAF59c75b00",
    "value": 5000,
    "validAfter": 0,
    "validBefore": int(time.time()) + 3600,
    "nonce": "0x" + "ab" * 32
}

payload_data = {
    "types": types,
    "domain": domain,
    "primaryType": "ReceiveWithAuthorization",
    "message": message
}
signable_msg = encode_typed_data(full_message=payload_data)
signed = Account.sign_message(signable_msg, key)

envelope = {
    "from": address,
    "signature": signed.signature.hex(),
    "data": payload_data
}

b64_header = base64.b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")

# 3. Send request to server.py
url = "http://localhost:8000/api/v1/extract"
body = json.dumps({
    "url": "https://news.ycombinator.com",
    "schema_spec": {"top_title": "Title of top story"}
}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=body,
    headers={
        "Content-Type": "application/json",
        "PAYMENT-SIGNATURE": b64_header
    },
    method="POST"
)

print("\nSending POST extraction request to server.py...")
try:
    with urllib.request.urlopen(req) as response:
        res_body = response.read().decode("utf-8")
        print(f"\n[FAIL] Guardrail breached! Request succeeded unexpectedly (Status {response.status}):")
        print(res_body)
except urllib.error.HTTPError as e:
    error_body = e.read().decode("utf-8")
    print("\n--- Guardrail Verification Result ---")
    print(f"Status Code: {e.code}")
    print(f"Detail:      {error_body}")
except Exception as e:
    print(f"\nUnexpected Connection Error: {e}")