import json
import base64
import time
import secrets
import os
import httpx
from pydantic import BaseModel, Field
from eth_account import Account
from eth_account.messages import encode_typed_data
from langchain_core.tools import tool  # For CrewAI: from crewai.tools import tool

def _sign_x402_payment(account, payment_spec: dict) -> str:
    """Internal helper to construct and sign EIP-712 USDC payment payload."""
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


class ExtractUrlSchema(BaseModel):
    target_url: str = Field(description="Target website URL to scrape and extract structured data from.")


@tool("x402_paid_web_extractor", args_schema=ExtractUrlSchema)
def x402_paid_web_extractor(target_url: str) -> str:
    """Scrapes structured web data from a target URL by paying a $0.005 USDC micro-fee via x402 Base L2."""
    gateway_url = os.getenv("GATEWAY_URL", "https://flight-dill-hangout.ngrok-free.dev/api/v1/extract")
    private_key = os.getenv("CLIENT_PRIVATE_KEY")
    
    if not private_key:
        return "Error: CLIENT_PRIVATE_KEY environment variable is not set."

    client_account = Account.from_key(private_key)

    with httpx.Client(timeout=120.0) as client:
        # Step 1: Initial unauthenticated request
        resp = client.get(gateway_url, params={"url": target_url})
        
        # Step 2: Handle x402 challenge
        if resp.status_code == 402:
            header_spec = resp.headers.get("PAYMENT-REQUIRED")
            payment_spec = json.loads(base64.b64decode(header_spec).decode("utf-8")) if header_spec else resp.json()["details"]
            
            # Step 3: Sign payload and resubmit
            sig_header = _sign_x402_payment(client_account, payment_spec)
            resp = client.get(gateway_url, params={"url": target_url}, headers={"PAYMENT-SIGNATURE": sig_header})

        if resp.status_code == 200:
            return json.dumps(resp.json())
        
        return f"Extraction failed with HTTP {resp.status_code}: {resp.text}"
