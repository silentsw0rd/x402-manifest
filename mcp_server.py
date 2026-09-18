# mcp_server.py
import os
from fastmcp import FastMCP
from x402_tool import x402_paid_web_extractor

mcp = FastMCP(
    "x402 Web Extractor",
    description="Paid web extraction gateway gated by x402 Base L2 USDC micropayments."
)

@mcp.tool()
def extract_web_data(target_url: str) -> str:
    """Scrapes and extracts structured data from a target URL by paying a $0.005 USDC micro-fee on Base L2."""
    return x402_paid_web_extractor.invoke({"target_url": target_url})

if __name__ == "__main__":
    # Run as a remote SSE server on port 8001
    mcp.run(transport="sse", host="0.0.0.0", port=8001)