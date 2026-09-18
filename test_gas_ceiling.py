import os
from settlement_worker import is_gas_price_acceptable, w3

print("=" * 50)
print(" Base L2 Gas Price Ceiling Test")
print("=" * 50)

current_gas_wei = w3.eth.gas_price
current_gwei = float(w3.from_wei(current_gas_wei, "gwei"))

print(f"Current Base L2 Gas Price: {current_gwei:.4f} Gwei")

# Test 1: Standard ceiling (1.5 Gwei)
os.environ["MAX_GAS_PRICE_GWEI"] = "1.5"
import settlement_worker
settlement_worker.MAX_GAS_PRICE_GWEI = 1.5

gas_ok, gwei = is_gas_price_acceptable()
print(f"\n[Test 1] Ceiling = 1.5 Gwei -> Executable: {gas_ok}")

# Test 2: Artificially low ceiling (0.0001 Gwei)
settlement_worker.MAX_GAS_PRICE_GWEI = 0.0001
gas_ok_low, gwei_low = is_gas_price_acceptable()
print(f"[Test 2] Ceiling = 0.0001 Gwei -> Executable: {gas_ok_low}")

if gas_ok and not gas_ok_low:
    print("\n[SUCCESS] Gas price ceiling guardrail operating correctly.")
else:
    print("\n[FAIL] Gas guardrail did not trigger expected state.")