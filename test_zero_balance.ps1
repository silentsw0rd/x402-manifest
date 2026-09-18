# test_zero_balance.ps1 - Tests balance guardrail against empty burner wallets

$PythonScript = @"
import json
import base64
import time
from eth_account import Account
from eth_account.messages import encode_typed_data

# 1. Generate brand new empty burner wallet (0 USDC balance)
burner = Account.create()
address = burner.address
key = burner.key.hex()

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

payload_data = {"types": types, "domain": domain, "primaryType": "ReceiveWithAuthorization", "message": message}
signable_msg = encode_typed_data(full_message=payload_data)
signed = Account.sign_message(signable_msg, key)

envelope = {
    "from": address,
    "signature": signed.signature.hex(),
    "data": payload_data
}

print(json.dumps({"address": address, "header": base64.b64encode(json.dumps(envelope).encode()).decode()}))
"@

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Generating Zero-Balance Burner Wallet            " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Execute signing python script
$Data = python -c "$PythonScript" | ConvertFrom-Json

Write-Host "Burner Address: $($Data.address)" -ForegroundColor Yellow
Write-Host "Sending POST extraction request to server.py..." -ForegroundColor Cyan

$Body = @{
    url = "https://news.ycombinator.com"
    schema_spec = @{ top_title = "Title of top story" }
} | ConvertTo-Json

try {
    $Response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/extract" `
        -Method POST `
        -Headers @{
            "Content-Type" = "application/json"
            "PAYMENT-SIGNATURE" = $Data.header
        } `
        -Body $Body
    
    Write-Host "`n[FAIL] Guardrail breached! Request succeeded unexpectedly." -ForegroundColor Red
} catch {
    Write-Host "`n--- Guardrail Verification Result ---" -ForegroundColor Green
    Write-Host "Status Code: " $_.Exception.Response.StatusCode.Value__ -ForegroundColor Red
    
    $Reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
    $ResponseBody =$Reader.ReadToEnd()
    Write-Host "Detail:      " $ResponseBody -ForegroundColor Yellow
}