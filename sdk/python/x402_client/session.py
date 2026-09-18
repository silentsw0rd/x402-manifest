import time
from eth_account import Account
from eth_account.messages import encode_typed_data

class SessionKeyManager:
    def __init__(self, root_private_key: str, budget_limit_wei: int, ttl_seconds: int = 3600):
        self.root_account = Account.from_key(root_private_key)
        self.ephemeral_account = Account.create()
        self.budget_limit_wei = budget_limit_wei
        self.spent_wei = 0
        self.expires_at = int(time.time()) + ttl_seconds
        
        # Authorize the session key with root account
        self.delegation_proof = self._generate_delegation_proof()

    def _generate_delegation_proof(self) -> str:
        # EIP-712 Delegation Grant
        typed_data = {
            "types": {
                "EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"}],
                "SessionGrant": [
                    {"name": "sessionKey", "type": "address"},
                    {"name": "budgetLimitWei", "type": "uint256"},
                    {"name": "expiresAt", "type": "uint256"}
                ]
            },
            "primaryType": "SessionGrant",
            "domain": {"name": "x402-Session", "version": "1"},
            "message": {
                "sessionKey": self.ephemeral_account.address,
                "budgetLimitWei": self.budget_limit_wei,
                "expiresAt": self.expires_at
            }
        }
        signable_msg = encode_typed_data(full_message=typed_data)
        signed = self.root_account.sign_message(signable_msg)
        return signed.signature.hex()

    def sign_payment_challenge(self, challenge_hash: bytes, price_wei: int) -> dict:
        if time.time() > self.expires_at:
            raise PermissionError("Session key expired.")
        if self.spent_wei + price_wei > self.budget_limit_wei:
            raise PermissionError("Session budget exceeded.")

        # Sign challenge with ephemeral key
        signed_challenge = self.ephemeral_account.signHash(challenge_hash)
        self.spent_wei += price_wei

        return {
            "session_key": self.ephemeral_account.address,
            "root_wallet": self.root_account.address,
            "delegation_proof": self.delegation_proof,
            "signature": signed_challenge.signature.hex(),
            "expires_at": self.expires_at
        }