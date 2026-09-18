import asyncio
import base64
import json
import os
import logging
import aiosqlite
from web3 import AsyncWeb3
from eth_account import Account
from dotenv import load_dotenv
from nonce_tracker import nonce_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("x402-worker")

load_dotenv()

RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
RELAYER_PRIVATE_KEY = os.getenv("RELAYER_PRIVATE_KEY") or os.getenv("AGENT_PRIVATE_KEY")
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DB_PATH = "storage/nonce_tracker.db"
MAX_GAS_PRICE_GWEI = float(os.getenv("MAX_GAS_PRICE_GWEI", "1.5"))

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


async def is_gas_price_acceptable(w3: AsyncWeb3) -> tuple[bool, float]:
    """Queries current network gas price asynchronously and checks against MAX_GAS_PRICE_GWEI."""
    try:
        current_gas_wei = await w3.eth.gas_price
        current_gas_gwei = float(w3.from_wei(current_gas_wei, "gwei"))
        
        if current_gas_gwei > MAX_GAS_PRICE_GWEI:
            return False, current_gas_gwei
        return True, current_gas_gwei
    except Exception as e:
        logger.error(f"Failed to fetch gas price from Base RPC: {e}")
        return False, 0.0


async def process_queue():
    if not RELAYER_PRIVATE_KEY:
        logger.error("RELAYER_PRIVATE_KEY is missing from .env file!")
        return

    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(RPC_URL))
    account = Account.from_key(RELAYER_PRIVATE_KEY)
    usdc = w3.eth.contract(address=w3.to_checksum_address(USDC_CONTRACT), abi=EIP3009_ABI)

    logger.info(f"Settlement Worker active. Relayer wallet: {account.address} | Gas Ceiling: {MAX_GAS_PRICE_GWEI} Gwei")

    while True:
        try:
            # 1. Check gas ceiling guardrail
            gas_ok, current_gwei = await is_gas_price_acceptable(w3)
            if not gas_ok:
                logger.warning(
                    f"Gas price ({current_gwei:.3f} Gwei) exceeds ceiling ({MAX_GAS_PRICE_GWEI} Gwei). Pausing settlements."
                )
                await asyncio.sleep(10)
                continue

            # 2. Process pending items in SQLite
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

                        tx_nonce = await w3.eth.get_transaction_count(account.address)
                        gas_price = await w3.eth.gas_price

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
                            "gasPrice": gas_price
                        })

                        signed_tx = account.sign_transaction(tx)
                        raw_tx = getattr(signed_tx, "raw_transaction", getattr(signed_tx, "rawTransaction", None))
                        tx_hash = await w3.eth.send_raw_transaction(raw_tx)
                        logger.info(f"Settled tx on Base L2! Hash: {tx_hash.hex()}")

                        await db.execute("UPDATE pending_settlements SET status='settled' WHERE id=?", (row_id,))
                        await db.commit()

                    except Exception as row_error:
                        logger.error(f"Error settling row {row_id}: {row_error}")
                        await db.execute("UPDATE pending_settlements SET status='failed' WHERE id=?", (row_id,))
                        await db.commit()

        except Exception as e:
            logger.error(f"Worker loop error: {e}")

        await asyncio.sleep(10)


if __name__ == "__main__":
    async def main():
        await nonce_db.init_db()
        await process_queue()

    asyncio.run(main())