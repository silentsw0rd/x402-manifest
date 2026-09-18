import asyncio
import os
from typing import List, Optional, Dict
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright

MODEL_NAME = "qwen2.5:14b"

# Single initialized Instructor client pointing to local Ollama instance
llm_client = instructor.from_openai(
    AsyncOpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    ),
    mode=instructor.Mode.JSON
)

class KeyMetric(BaseModel):
    label: str = Field(description="Name or category of the metric (e.g., Price, Rating, Rank)")
    value: str = Field(description="Extracted value associated with the metric")

class ArticleMetadata(BaseModel):
    author: Optional[str] = Field(default=None, description="Name of the article author")
    publish_date: Optional[str] = Field(default=None, description="Publication date formatted as YYYY-MM-DD")
    reading_time_minutes: Optional[int] = Field(default=None, description="Estimated reading time in minutes")

class ProductSpec(BaseModel):
    product_name: str = Field(description="Exact name or title of the item")
    price: Optional[float] = Field(default=None, description="Numerical price value excluding currency symbols (e.g., 29.99)")
    currency: str = Field(default="USD", description="Currency symbol or code (e.g., USD, EUR, $)")
    in_stock: bool = Field(default=True, description="True if available to buy, False if sold out")
    features: List[str] = Field(default=[], description="Key product feature bullet points")

class WebPageExtraction(BaseModel):
    page_type: str = Field(description="Categorize page: 'product', 'article', 'forum', or 'other'")
    title: str = Field(description="Main title or header of the page")
    article: Optional[ArticleMetadata] = Field(default=None, description="Populate only if page is an article")
    product: Optional[ProductSpec] = Field(default=None, description="Populate only if page is a product listing")
    summary: str = Field(description="2-3 sentence overview of page contents")

class ProxyManager:
    """Manages pool of residential/datacenter HTTP proxies for Playwright."""
    def __init__(self, proxy_list: Optional[List[str]] = None):
        self.proxies = proxy_list or os.getenv("PROXY_POOL", "").split(",")
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
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())[:8000]

async def fetch_and_clean_dom(url: str) -> str:
    proxy_config = proxy_mgr.get_next_proxy()
    if proxy_config:
        print(f"[+] Launching Playwright via Proxy: {proxy_config['server']}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy_config
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        raw_html = await page.content()
        await browser.close()
    
    return prune_dom(raw_html)

async def extract_web_data(url: str) -> WebPageExtraction:
    clean_text = await fetch_and_clean_dom(url)
    
    extracted_data: WebPageExtraction = await llm_client.chat.completions.create(
        model=MODEL_NAME,
        response_model=WebPageExtraction,
        max_retries=2,
        messages=[
            {
                "role": "system",
                "content": "You are a precise data extraction engine. Extract key details into the requested JSON schema."
            },
            {
                "role": "user",
                "content": f"URL: {url}\n\nExtract structured data from this webpage content:\n\n{clean_text}"
            }
        ]
    )
    
    return extracted_data