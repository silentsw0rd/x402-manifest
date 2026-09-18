# x402 Web Extraction Tool for Autonomous Agents

An automated, structured web-scraping service built for AI agents. This gateway utilizes local Playwright browser automation combined with Ollama (`qwen2.5:14b`) structured parsing, gated by **x402 micropayments on Base L2**.

---

## 🤖 Agent Discovery & Schemas

Autonomous agents and integration frameworks (Composio, GPT Actions, LangChain, CrewAI) can discover and ingest this tool using the following machine-readable endpoints:

* **x402 Protocol Manifest:** `https://silentsw0rd.github.io/x402-manifest/.well-known/x402.json`
* **OpenAPI 3.0 Specification:** `https://flight-dill-hangout.ngrok-free.dev/openapi.json`

---

## 💳 Payment Specifications

Requests require an EIP-712 payment authorization signed by the buyer agent via EIP-3009 (`receiveWithAuthorization`).

| Parameter | Value |
| :--- | :--- |
| **Network** | Base Mainnet (`eip155:8453`) |
| **Payment Token** | USD Coin (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`) |
| **Price per Call** | $0.005 USDC (`5000` base units) |
| **Pay To Address** | `0xd2eA78C3eeA0Ed3275b2465915527eAF59c75b00` |

---

## 🔌 API Endpoint

### Extract Web Data

`GET https://flight-dill-hangout.ngrok-free.dev/api/v1/extract`

**Query Parameters:**
* `url` *(string, required)*: The full HTTP/HTTPS URL to scrape and extract.

**Headers:**
* `PAYMENT-SIGNATURE` *(string, required for execution)*: Base64-encoded JSON envelope containing the buyer's address, EIP-712 payload data, and signature.

---

## 🔄 x402 Challenge & Handshake Loop

1. **Initial Challenge:** Send an unauthenticated `GET` request to `/api/v1/extract?url=<target_url>`.
2. **HTTP 402 Response:** The server returns status `402 Payment Required` containing the payment spec inside the `PAYMENT-REQUIRED` response header.
3. **Cryptographic Signing:** Construct an EIP-712 `ReceiveWithAuthorization` domain payload for 5,000 USDC units and sign it using your client wallet private key.
4. **Authorized Request:** Resubmit the `GET` request including the `PAYMENT-SIGNATURE` header.
5. **Execution & Settlement:** The gateway validates the signature off-chain, runs the web scraper, returns structured JSON data, and queues the payment for background on-chain settlement.

---
{
  "mcpServers": {
    "x402-web-extractor": {
      "url": "https://flight-dill-hangout.ngrok-free.dev/sse"
    }
  }
}
---

## 📦 Python Client Integration

```python
import httpx
import os

from x402_tool import x402_paid_web_extractor

os.environ["CLIENT_PRIVATE_KEY"] = "0xYourWalletPrivateKey"
os.environ["GATEWAY_URL"] = "[https://flight-dill-hangout.ngrok-free.dev/api/v1/extract](https://flight-dill-hangout.ngrok-free.dev/api/v1/extract)"

# Execute paid web extraction
result = x402_paid_web_extractor.invoke({"target_url": "[https://news.ycombinator.com](https://news.ycombinator.com)"})
print(result)
