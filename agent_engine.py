import os
import json
import logging
from typing import Any, List, Optional, Dict
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
import instructor
from pydantic import create_model, BaseModel, Field, ValidationError
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logger = logging.getLogger("x402-agent-engine")

MODEL_NAME = "qwen2.5:14b"

# Async Instructor client pointing to local Ollama instance (non-blocking)
async_llm_client = instructor.from_openai(
    AsyncOpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    ),
    mode=instructor.Mode.JSON
)

class ProxyManager:
    """Manages pool of residential/datacenter HTTP proxies for Playwright."""
    def __init__(self, proxy_list: Optional[List[str]] = None):
        raw_pool = os.getenv("PROXY_POOL", "")
        self.proxies = proxy_list or (raw_pool.split(",") if raw_pool else [])
        self.proxies = [p.strip() for p in self.proxies if p.strip()]
        self._index = 0

    def get_next_proxy(self) -> Optional[Dict[str, str]]:
        if not self.proxies:
            return None
        proxy_url = self.proxies[self._index % len(self.proxies)]
        self._index += 1
        return {"server": proxy_url}

proxy_mgr = ProxyManager()

def prune_dom(html_content: str) -> str:
    """Removes scripts, styles, and non-content tags to clean prompt context."""
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())[:8000]


def build_pydantic_from_dict(schema_spec: Dict[str, Any]) -> type[BaseModel]:
    """Dynamically builds a Pydantic model for Instructor validation."""
    fields = {}
    for key, desc in schema_spec.items():
        description_str = desc if isinstance(desc, str) else str(desc)
        fields[key] = (str, Field(description=description_str))
    return create_model("DynamicSchema", **fields)


async def extract_web_data(url: str, schema_spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Renders target URL via stealth Playwright with proxy rotation, cleans DOM,

    and extracts structured data via Async Instructor. Raises exceptions on failure to abort x402 settlement.
    """
    cleaned_text = ""
    proxy_config = proxy_mgr.get_next_proxy()

    # 1. Stealth Playwright Browser Execution with Proxy Support
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy_config,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/Chicago"
        )
        page = await context.new_page()

        # Patch bot indicators using the v2 API
        await Stealth().apply_stealth_async(page)

        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if not response or response.status >= 400:
                status_code = response.status if response else "N/A"
                raise RuntimeError(f"Target site blocked request or returned HTTP status {status_code}")

            await page.wait_for_timeout(2000)
            raw_html = await page.content()
            cleaned_text = prune_dom(raw_html)
        finally:
            await browser.close()

    if not cleaned_text.strip():
        raise ValueError("Scraper retrieved empty page content")

    # Return unstructured text snippet if caller provided no schema
    if not schema_spec:
        return {
            "summary": cleaned_text[:2000],
            "status": "unstructured_raw"
        }

    # 2. Async Non-Blocking Instructor Call with Dynamic Pydantic Schema
    TargetModel = build_pydantic_from_dict(schema_spec)
    
    try:
        extracted_result = await async_llm_client.chat.completions.create(
            model=MODEL_NAME,
            response_model=TargetModel,
            messages=[
                {
                    "role": "system",
                    "content": "Extract structured information from the provided web content matching the target schema exactly."
                },
                {
                    "role": "user",
                    "content": f"CONTENT:\n{cleaned_text}"
                }
            ],
            max_retries=2
        )
        return {
            "status": "validated",
            "extracted_data": extracted_result.model_dump()
        }
    except (ValidationError, Exception) as e:
        logger.error(f"Instructor LLM extraction failed: {str(e)}")
        raise ValueError(f"Extracted payload failed schema validation: {str(e)}")