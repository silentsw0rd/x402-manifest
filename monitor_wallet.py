import asyncio
import os
from web3 import AsyncWeb3
from dotenv import load_dotenv

load_dotenv()

# Public Base Mainnet RPC
RPC_URL = "https://mainnet.base.org"
RECEIVER_ADDRESS = os.getenv("RECEIVER_ADDRESS")
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Minimal ERC-20 ABI for checking balance
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

async def monitor_balance():
    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(RPC_URL))
    checksum_address = w3.to_checksum_address(RECEIVER_ADDRESS)
    contract = w3.eth.contract(address=w3.to_checksum_address(USDC_CONTRACT), abi=ERC20_ABI)

    print(f"[*] Monitoring Base L2 USDC balance for: {checksum_address}")
    last_balance = None

    while True:
        try:
            # Query on-chain balance (USDC has 6 decimals)
            raw_balance = await contract.functions.balanceOf(checksum_address).call()
            usdc_balance = raw_balance / 1e6

            if last_balance is not None and usdc_balance > last_balance:
                earned = usdc_balance - last_balance
                print(f"[💰 PAYMENT RECEIVED] +${earned:.4f} USDC! New Balance: ${usdc_balance:.4f} USDC")
            elif last_balance is None:
                print(f"[+] Current Wallet Balance: ${usdc_balance:.4f} USDC")

            last_balance = usdc_balance
        except Exception as e:
            print(f"[!] Error fetching on-chain data: {e}")

        await asyncio.sleep(15)  # Poll every 15 seconds

if __name__ == "__main__":
    asyncio.run(monitor_balance())