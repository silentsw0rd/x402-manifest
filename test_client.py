import json
import base64
import time
import secrets
import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data

# Replace secrets.token_hex(32) with a fixed 32-byte hex key
TEST_PRIVATE_KEY = "0x162fe10155bb8b88306384a8634ee5b7a964f6af5143085e13005d7709a52562" # Sample static dev key
test_account = Account.from_key(TEST_PRIVATE_KEY)

GATEWAY_URL = "https://flight-dill-hangout.ngrok-free.dev/api/v1/extract"
TARGET_URL = "http://localhost:9999/nonexistent"

import copy

def create_eip712_payment_payload(account, payment_spec: dict) -> str:
    """Constructs and cryptographically signs an EIP-712 ReceiveWithAuthorization payload."""
    accept_spec = payment_spec["accepts"][0]
    
    chain_id = int(accept_spec["network"].split(":")[-1])
    verifying_contract = accept_spec["asset"]
    recipient = accept_spec["payTo"]
    amount = int(accept_spec["amount"])
    
    nonce = "0x" + secrets.token_hex(32)
    valid_before = int(time.time()) + 3600

    typed_data = {
        "types": {
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
        },
        "domain": {
            "name": "USD Coin",
            "version": "2",
            "chainId": chain_id,
            "verifyingContract": verifying_contract
        },
        "primaryType": "ReceiveWithAuthorization",
        "message": {
            "from": account.address,
            "to": recipient,
            "value": amount,
            "validAfter": 0,
            "validBefore": valid_before,
            "nonce": nonce
        }
    }

    signable_message = encode_typed_data(full_message=typed_data)
    signed_msg = account.sign_message(signable_message)

    payload_envelope = {
        "from": account.address,
        "signature": signed_msg.signature.hex(),
        "data": typed_data
    }

    return base64.b64encode(json.dumps(payload_envelope).encode("utf-8")).decode("utf-8")

    return base64.b64encode(json.dumps(payload_envelope).encode("utf-8")).decode("utf-8")

    # Cryptographically sign the typed EIP-712 structure
    signable_message = encode_typed_data(full_message=typed_data)
    signed_msg = account.sign_message(signable_message)

    payload_envelope = {
        "from": account.address,
        "signature": signed_msg.signature.hex(),
        "data": typed_data
    }

    # Encode envelope into Base64 for the payment header
    return base64.b64encode(json.dumps(payload_envelope).encode("utf-8")).decode("utf-8")

def run_test_harness():
    print(f"[*] Client initialized with wallet address: {test_account.address}")
    
    with httpx.Client(timeout=120.0) as client:
        # 1. Initial Unauthenticated Request (Expect 402)
        print(f"[*] Step 1: Sending initial unauthenticated request to gateway...")
        resp = client.get(GATEWAY_URL, params={"url": TARGET_URL})
        
        if resp.status_code != 402:
            print(f"[X] Unexpected initial response status {resp.status_code}: {resp.text}")
            return

        print("[!] Caught HTTP 402 Payment Required challenge.")
        header_spec = resp.headers.get("PAYMENT-REQUIRED")
        payment_spec = json.loads(base64.b64decode(header_spec).decode("utf-8")) if header_spec else resp.json()["details"]
        print(f"[+] Payment Required Spec: {payment_spec['accepts'][0]['humanReadableAmount']} to {payment_spec['accepts'][0]['payTo']}")

        # 2. Construct & Sign EIP-712 Payment Payload
        signature_header = create_eip712_payment_payload(test_account, payment_spec)
        print("[+] Signed EIP-712 authorization payload successfully.")

        # 3. Resubmit Request with Payment Signature Header
        print("[*] Step 2: Resubmitting request with PAYMENT-SIGNATURE header...")
        paid_resp = client.get(
            GATEWAY_URL,
            params={"url": TARGET_URL},
            headers={"PAYMENT-SIGNATURE": signature_header}
        )

        if paid_resp.status_code == 200:
            print("[✓] Request Successful! (HTTP 200 OK)")
            settlement_header = paid_resp.headers.get("PAYMENT-RESPONSE")
            if settlement_header:
                decoded_settlement = json.loads(base64.b64decode(settlement_header).decode("utf-8"))
                print(f"[+] Settlement Confirmation Header: {decoded_settlement}")
            
            print("\n--- Extracted Data JSON Response ---")
            print(json.dumps(paid_resp.json(), indent=2))
        else:
            print(f"[X] Payment request failed: HTTP {paid_resp.status_code} - {paid_resp.text}")
            return

        # 4. Anti-Replay Verification Step (Reusing the exact same signature)
        print("\n[*] Step 3: Verifying Anti-Replay Defense by reusing the same payment signature...")
        replay_resp = client.get(
            GATEWAY_URL,
            params={"url": TARGET_URL},
            headers={"PAYMENT-SIGNATURE": signature_header}
        )
        if replay_resp.status_code == 403:
            print(f"[✓] Replay defense verified! Gateway correctly rejected reused signature (HTTP 403): {replay_resp.json()['detail']}")
        else:
            print(f"[X] Replay protection failed! Status code: {replay_resp.status_code}")

if __name__ == "__main__":
    run_test_harness()