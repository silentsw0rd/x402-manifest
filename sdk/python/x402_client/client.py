import json
import base64
import time
import requests
from eth_account import Account
from eth_account.messages import encode_typed_data
from typing import Dict, Any, Optional

class X402Client:
    def __init__(self, private_key: str, gateway_url: str):
        self.account = Account.from_key(private_key)
        self.gateway_url = gateway_url.rstrip("/")

    def _sign_eip712_challenge(self, payment_spec: Dict[str, Any]) -> str:
        accept_spec = payment_spec["accepts"][0]
        chain_id = int(accept_spec["network"].split(":")[-1])
        
        domain = {
            "name": "USD Coin",
            "version": "2",
            "chainId": chain_id,
            "verifyingContract": accept_spec["asset"]
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
            "from": self.account.address,
            "to": accept_spec["payTo"],
            "value": int(accept_spec["amount"]),
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
        signed = Account.sign_message(signable_msg, self.account.key.hex())

        envelope = {
            "from": self.account.address,
            "signature": signed.signature.hex(),
            "data": payload_data
        }
        return base64.b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")

    def extract(self, url: str, schema_spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        endpoint = f"{self.gateway_url}/api/v1/extract"
        payload = {"url": url, "schema_spec": schema_spec}

        # Initial Request
        res = requests.post(endpoint, json=payload)

        # Intercept 402 Payment Challenge
        if res.status_code == 402:
            raw_header = res.headers.get("PAYMENT-REQUIRED")
            spec = json.loads(base64.b64decode(raw_header).decode("utf-8")) if raw_header else res.json().get("spec")
            
            # Sign challenge and retry
            sig_header = self._sign_eip712_challenge(spec)
            res = requests.post(
                endpoint, 
                json=payload, 
                headers={"PAYMENT-SIGNATURE": sig_header}
            )

        res.raise_for_status()
        return res.json()