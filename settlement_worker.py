import asyncio
import base64
import json
import os
import aiosqlite
from web3 import AsyncWeb3
from eth_account import Account
from dotenv import load_dotenv

load_dotenv()

RPC_URL = "https://mainnet.base.org"
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PRIVATE_KEY = os.getenv("AGENT_PRIVATE_KEY")
DB_PATH = "storage/nonce_tracker.db"

# Minimal ABI for EIP-3009 receiveWithAuthorization
EIP3009_ABI = [
    {
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
            {"name": "v", "type": "uint8"},
            {"name": "r", "type": "bytes32"},
            {"name": "s", "type": "bytes32"}
        ],
        "name": "receiveWithAuthorization",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

def split_signature(sig_hex: str):
    sig_bytes = bytes.fromhex(sig_hex.replace("0x", ""))
    r = sig_bytes[:32]
    s = sig_bytes[32:64]
    v = sig_bytes[64]
    if v < 27:
        v += 27
    return v, r, s

async def process_queue():
    if not PRIVATE_KEY:
        print("[!] Error: AGENT_PRIVATE_KEY is missing from .env file!")
        return

    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(RPC_URL))
    account = Account.from_key(PRIVATE_KEY)
    usdc = w3.eth.contract(address=w3.to_checksum_address(USDC_CONTRACT), abi=EIP3009_ABI)

    print(f"[*] Settlement Worker active. Relayer wallet: {account.address}")

    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT id, payment_header FROM pending_settlements WHERE status='pending' LIMIT 5"
                ) as cursor:
                    rows = await cursor.fetchall()

                for row_id, payment_header in rows:
                    try:
                        raw = json.loads(base64.b64decode(payment_header).decode("utf-8"))
                        msg = raw["data"]["message"]
                        sig = raw["signature"]

                        nonce_hex = msg["nonce"].replace("0x", "").zfill(64)
                        nonce_bytes = bytes.fromhex(nonce_hex)

                        v, r, s = split_signature(sig)

                        # Fetch transaction nonce for relayer wallet
                        tx_nonce = await w3.eth.get_transaction_count(account.address)

                        # Build transaction
                        tx = await usdc.functions.receiveWithAuthorization(
                            w3.to_checksum_address(msg["from"]),
                            w3.to_checksum_address(msg["to"]),
                            int(msg["value"]),
                            int(msg.get("validAfter", 0)),
                            int(msg.get("validBefore", 0)),
                            nonce_bytes,
                            v,
                            r,
                            s
                        ).build_transaction({
                            "from": account.address,
                            "nonce": tx_nonce,
                            "chainId": 8453,
                            "gasPrice": await w3.eth.gas_price
                        })

                        signed_tx = account.sign_transaction(tx)
                        raw_tx = getattr(signed_tx, "raw_transaction", getattr(signed_tx, "rawTransaction", None))
                        tx_hash = await w3.eth.send_raw_transaction(raw_tx)
                        print(f"[+] Settled tx on Base L2! Hash: {tx_hash.hex()}")

                        # Mark as settled in SQLite
                        await db.execute("UPDATE pending_settlements SET status='settled' WHERE id=?", (row_id,))
                        await db.commit()

                    except Exception as row_error:
                        print(f"[!] Error settling row {row_id}: {row_error}")
                        # Mark as failed to prevent infinite retry loops on bad signatures
                        await db.execute("UPDATE pending_settlements SET status='failed' WHERE id=?", (row_id,))
                        await db.commit()

        except Exception as e:
            print(f"[!] Worker loop error: {e}")

        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(process_queue())