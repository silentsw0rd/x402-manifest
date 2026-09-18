import json
import base64
import os
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field, create_model
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_typed_data
from dotenv import load_dotenv

from agent_engine import extract_web_data as run_agent_extraction
from nonce_tracker import nonce_db

logger = logging.getLogger("x402-server")

# Load environment variables
load_dotenv()
os.makedirs("storage", exist_ok=True)

# Mainnet USDC Configuration
RECEIVER_ADDRESS = os.getenv("RECEIVER_ADDRESS", "0xd2eA78C3eeA0Ed3275b2465915527eAF59c75b00")
USDC_BASE_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_CHAIN_ID = 8453
PRICE_USDC_UNITS = 5000


class ExtractPayload(BaseModel):
    url: str = Field(..., description="Target URL to scrape.")
    schema_spec: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Dictionary mapping field names to descriptions or type specs."
    )


def build_dynamic_pydantic_model(schema_spec: Optional[Dict[str, Any]]) -> type[BaseModel]:
    """Generates a dynamic Pydantic model at runtime from a user-provided dict."""
    if not schema_spec:
        class DefaultSchema(BaseModel):
            title: str = Field(description="Main page title or heading")
            summary: str = Field(description="Brief summary of main content")
            key_points: list[str] = Field(description="List of key facts or topics")
        return DefaultSchema

    fields = {}
    for field_name, field_info in schema_spec.items():
        if isinstance(field_info, str):
            fields[field_name] = (str, Field(description=field_info))
        elif isinstance(field_info, dict):
            desc = field_info.get("description", f"Extracted {field_name}")
            fields[field_name] = (str, Field(description=desc))
        else:
            fields[field_name] = (str, Field(description=f"Extracted {field_name}"))

    return create_model("DynamicExtractionModel", **fields)


def build_x402_spec() -> Dict[str, Any]:
    spec = {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": f"eip155:{BASE_CHAIN_ID}",
            "asset": USDC_BASE_CONTRACT,
            "amount": str(PRICE_USDC_UNITS),
            "payTo": RECEIVER_ADDRESS
        }]
    }
    encoded = base64.b64encode(json.dumps(spec).encode("utf-8")).decode("utf-8")
    return {"encoded_header": encoded, "raw": spec}


def verify_and_parse_eip712(payment_signature_b64: str) -> Tuple[str, str, int]:
    try:
        raw_payload = json.loads(base64.b64decode(payment_signature_b64).decode("utf-8"))
        signer_address = raw_payload.get("from")
        signature = raw_payload.get("signature")
        payload_data = raw_payload.get("data")
        
        msg = payload_data["message"]
        if payload_data["domain"]["verifyingContract"].lower() != USDC_BASE_CONTRACT.lower():
            raise ValueError("Mismatched token contract")
        if int(payload_data["domain"]["chainId"]) != BASE_CHAIN_ID:
            raise ValueError("Mismatched chain ID")
        if msg["to"].lower() != RECEIVER_ADDRESS.lower():
            raise ValueError("Mismatched payment recipient")
        if int(msg["value"]) < PRICE_USDC_UNITS:
            raise ValueError("Insufficient payment amount")

        signable_message = encode_typed_data(full_message=payload_data)
        recovered_address = Account.recover_message(signable_message, signature=signature)
        
        if recovered_address.lower() != signer_address.lower():
            raise ValueError("Invalid signature recovery")
            
        nonce = str(msg.get("nonce", signature[:10]))
        valid_before = int(msg.get("validBefore", 0))
        
        return recovered_address, nonce, valid_before
    except Exception as e:
        raise ValueError(f"Malformed EIP-712 envelope: {str(e)}")


def verify_payment_signature(sig_header: str) -> Dict[str, Any]:
    """Helper wrapper for EIP-712 signature verification."""
    try:
        signer, nonce, valid_before = verify_and_parse_eip712(sig_header)
        return {"is_valid": True, "from": signer, "nonce": nonce, "reason": None}
    except Exception as e:
        return {"is_valid": False, "from": None, "nonce": None, "reason": str(e)}


def queue_settlement_in_db(client_address: str, signature_envelope: str, nonce: str):
    """Queues verified signature into SQLite for background broadcasting."""
    # Add record to pending settlements database
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await nonce_db.init_db()
    print("[+] Nonce Database Initialized.")
    yield


app = FastAPI(
    title="x402 Local Web Scraping & Data Extraction Agent",
    description="Autonomous web extraction tool monetized via x402 HTTP micropayments on Base L2.",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/.well-known/x402.json", include_in_schema=False)
async def x402_well_known():
    return {
        "version": "2.0",
        "services": [{
            "name": "web_extraction_agent",
            "description": "Renders JS-heavy sites via Playwright and extracts clean JSON.",
            "endpoint": "/api/v1/extract",
            "method": "POST",
            "payment": {
                "network": f"eip155:{BASE_CHAIN_ID}",
                "asset": USDC_BASE_CONTRACT,
                "amount": str(PRICE_USDC_UNITS),
                "humanReadableAmount": "$0.005 USDC",
                "payTo": RECEIVER_ADDRESS
            }
        }]
    }


@app.get("/", include_in_schema=False)
async def root():
    return {
        "status": "online",
        "service": "x402 Web Extraction Gateway",
        "docs": "/docs",
        "openapi_spec": "/openapi.json"
    }


@app.get("/api/v1/extract")
async def extract_web_data_get(url: str, request: Request):
    sig_header = request.headers.get("PAYMENT-SIGNATURE")
    
    if not sig_header:
        payment_spec = build_x402_spec()
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_spec["encoded_header"]},
            content={"detail": "Payment required", "spec": payment_spec["raw"]}
        )

    validation_result = verify_payment_signature(sig_header)
    if not validation_result["is_valid"]:
        raise HTTPException(status_code=400, detail=validation_result["reason"])

    try:
        extracted_data = await run_agent_extraction(url)
        if not extracted_data:
            raise ValueError("Scraper returned an empty payload")
    except Exception as e:
        logger.error(f"Extraction failed for {url}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Web extraction failed: {str(e)}. Wallet was NOT charged."
        )

    queue_settlement_in_db(
        client_address=validation_result["from"],
        signature_envelope=sig_header,
        nonce=validation_result["nonce"]
    )
    return JSONResponse(status_code=200, content=extracted_data)


@app.post("/api/v1/extract")
async def extract_web_data_post(payload: ExtractPayload, request: Request):
    sig_header = request.headers.get("PAYMENT-SIGNATURE")
    
    if not sig_header:
        payment_spec = build_x402_spec()
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_spec["encoded_header"]},
            content={"detail": "Payment required", "spec": payment_spec["raw"]}
        )

    validation_result = verify_payment_signature(sig_header)
    if not validation_result["is_valid"]:
        raise HTTPException(status_code=400, detail=validation_result["reason"])

    target_model = build_dynamic_pydantic_model(payload.schema_spec)

    try:
        extracted_data = await run_agent_extraction(
            url=payload.url, 
            response_model=target_model
        )
        if not extracted_data:
            raise ValueError("Scraper returned an empty payload")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}. Payment signature was NOT charged."
        )

    queue_settlement_in_db(
        client_address=validation_result["from"],
        signature_envelope=sig_header,
        nonce=validation_result["nonce"]
    )
    return JSONResponse(status_code=200, content=extracted_data)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)