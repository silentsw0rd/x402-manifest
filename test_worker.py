import asyncio
import os
import aiosqlite
from settlement_worker import (
    is_gas_price_acceptable,
    RPC_URL,
    DB_PATH,
    MAX_GAS_PRICE_GWEI,
    EIP3009_ABI,
    USDC_CONTRACT
)
from web3 import AsyncWeb3
from nonce_tracker import nonce_db

async def test_worker_components():
    print("=" * 50)
    print(" Settlement Worker Execution Test")
    print("=" * 50)

    # 1. Initialize DB schema
    await nonce_db.init_db()
    print("[1/3] Nonce database initialized successfully.")

    # 2. Test Base L2 RPC connection & Gas Ceiling
    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(RPC_URL))
    connected = await w3.is_connected()
    print(f"[2/3] Base L2 RPC Connected: {connected}")

    if connected:
        gas_ok, current_gwei = await is_gas_price_acceptable(w3)
        print(f"      Current Gas Price: {current_gwei:.4f} Gwei (Ceiling: {MAX_GAS_PRICE_GWEI} Gwei)")
        print(f"      Gas Check Status: {'PASS' if gas_ok else 'PAUSED (Gas too high)'}")

    # 3. Test SQLite queue read operation
    print("[3/3] Checking pending settlement queue in SQLite...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM pending_settlements WHERE status='pending'") as cursor:
            count = await cursor.fetchone()
            print(f"      Pending settlements waiting in DB: {count[0]}")

    print("\n[SUCCESS] All worker modules initialized and executed without errors.")

if __name__ == "__main__":
    asyncio.run(test_worker_components())