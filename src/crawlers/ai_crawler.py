"""
AI Crawler
----------
Intent-aware crawler for non-conventional ecommerce websites.

- Jina: fast URL discovery + page content
- Gemini: semantic relevance + page classification
- Supports PRODUCT and OFFERING (project-style products)
"""

import os
import json
from typing import List, Dict, Set
from dataclasses import dataclass

import google.generativeai as genai

from src.utils.http_client import JinaClient
from src.utils.url_utils import normalize_url, same_domain


# ------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------

@dataclass
class PageDecision:
    url: str
    page_type: str          # PRODUCT | OFFERING | BLOG | INFO
    confidence: float
    summary: Dict


@dataclass
class AICrawlResult:
    accepted_pages: List[PageDecision]
    rejected_urls: List[str]


# ------------------------------------------------------------------
# AI Crawler
# ------------------------------------------------------------------

class AICrawler:
    """
    AI-powered crawler for sites where products are:
    - projects
    - case studies
    - custom offerings
    - blog-style pages
    """

    def __init__(
        self,
        jina_api_key: str = None,
        gemini_api_key: str = None,
        model_name: str = "gemini-2.5-flash",
        use_cache: bool = True
    ):
        # Jina API key is optional (r.jina.ai is free to use)
        self.jina = JinaClient(api_key=jina_api_key, use_cache=use_cache)
        self.use_cache = use_cache

        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel(model_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl(
        self,
        base_url: str,
        user_intent: str,
        max_urls: int = 50
    ) -> Set[str]:
        """
        Discover URLs → classify pages → return product/offering URLs.
        
        Returns Set[str] of URLs (same format as WebCrawler for interchangeability)
        """

        discovered_urls = self._discover_urls(base_url, max_urls)

        print(f"\n  Fetching page titles for {len(discovered_urls)} URLs...")
        
        # Fetch titles quickly with Jina
        url_info = []
        for i, url in enumerate(discovered_urls, 1):
            try:
                page = self.jina.fetch(url)
                url_info.append({
                    "url": url,
                    "title": page.title,
                    "snippet": page.text[:500]  # First 500 chars for context
                })
                print(f"  [{i}/{len(discovered_urls)}] ✓ {url}")
            except Exception as e:
                print(f"  [{i}/{len(discovered_urls)}] ✗ {url} - {e}")
                continue

        if not url_info:
            print("  ✗ No URLs could be fetched")
            return set()

        # Batch classify all URLs in ONE Gemini call
        print(f"\n  Classifying {len(url_info)} URLs with Gemini (batch mode)...")
        decisions = self._batch_classify_pages(url_info, user_intent)

        product_urls: Set[str] = set()
        
        for decision in decisions:
            if decision.page_type in ("PRODUCT", "OFFERING") and decision.confidence >= 0.6:
                product_urls.add(decision.url)
                print(f"    ✓ {decision.url}")
                print(f"      → {decision.page_type} (confidence: {decision.confidence:.0%})")
            else:
                print(f"    ⏭️  {decision.url} - {decision.page_type} (skipped)")

        print(f"\n  ✓ AI Classification complete: {len(product_urls)} product/offering pages found")
        return product_urls

    # ------------------------------------------------------------------
    # URL Discovery (Jina)
    # ------------------------------------------------------------------

    def _discover_urls(self, base_url: str, max_urls: int) -> List[str]:
        """
        Uses Jina to extract URLs from base page
        """
        response = self.jina.fetch(base_url)

        urls: Set[str] = set()

        for link in response.links:
            url = normalize_url(link)
            if not url:
                continue
            if same_domain(base_url, url):
                urls.add(url)
            if len(urls) >= max_urls:
                break

        return list(urls)

    # ------------------------------------------------------------------
    # Page Classification (Gemini)
    # ------------------------------------------------------------------

    def _batch_classify_pages(
        self,
        url_info: List[Dict],
        user_intent: str
    ) -> List[PageDecision]:
        """
        Batch classify multiple URLs in a single Gemini call.
        Much more efficient than individual calls.
        """

        # Build URL list for prompt
        url_list = ""
        for i, info in enumerate(url_info, 1):
            url_list += f"{i}. URL: {info['url']}\n"
            url_list += f"   Title: {info['title']}\n"
            url_list += f"   Snippet: {info['snippet'][:200]}...\n\n"

        prompt = f"""
You are classifying multiple webpages for data extraction.

USER INTENT:
{user_intent}

URLS TO CLASSIFY:
{url_list}

DEFINITIONS:

PRODUCT:
- Standard sellable product
- May or may not have a price

OFFERING:
- Project, case study, or example of work
- Represents a repeatable service or customizable product
- Customers can request "something like this"
- Pricing is usually custom or not shown

BLOG:
- Informational, editorial, educational
- Not directly sellable

INFO:
- About, contact, careers, policies

TASK:
Classify EACH URL as ONE of: PRODUCT, OFFERING, BLOG, INFO

OUTPUT STRICT JSON ARRAY:

[
  {{
    "url_number": 1,
    "page_type": "PRODUCT|OFFERING|BLOG|INFO",
    "confidence": 0.85,
    "name": "Short product/offering name or title"
  }},
  ...
]

RULES:
- Return array with {len(url_info)} items (one per URL)
- confidence must be between 0.0 and 1.0
- Keep name concise (max 50 chars)
- NO explanations, ONLY JSON array
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json"
                }
            )

            classifications = json.loads(response.text)
            
            decisions = []
            for item in classifications:
                url_num = item.get("url_number", 0) - 1  # Convert to 0-indexed
                if 0 <= url_num < len(url_info):
                    decisions.append(PageDecision(
                        url=url_info[url_num]["url"],
                        page_type=item.get("page_type", "INFO"),
                        confidence=float(item.get("confidence", 0.0)),
                        summary={"name": item.get("name", "")}
                    ))
            
            return decisions

        except Exception as e:
            print(f"  ✗ Batch classification failed: {e}")
            # Fallback: return empty list
            return []

    def _classify_page(
        self,
        url: str,
        user_intent: str
    ) -> PageDecision | None:
        """
        Fetch page content and let Gemini decide:
        - Is this PRODUCT / OFFERING / BLOG / INFO
        """

        try:
            page = self.jina.fetch(url)
        except Exception:
            return None

        prompt = f"""
You are classifying a webpage for data extraction.

USER INTENT:
{user_intent}

URL:
{url}

PAGE TITLE:
{page.title}

PAGE CONTENT:
{page.text[:4000]}

DEFINITIONS:

PRODUCT:
- Standard sellable product
- May or may not have a price

OFFERING:
- Project, case study, or example of work
- Represents a repeatable service or customizable product
- Customers can request "something like this"
- Pricing is usually custom or not shown

BLOG:
- Informational, editorial, educational
- Not directly sellable

INFO:
- About, contact, careers, policies

TASK:
1. Classify the page as ONE of:
   PRODUCT, OFFERING, BLOG, INFO
2. Decide if this page should be KEPT for extraction
3. If PRODUCT or OFFERING, extract a short summary

OUTPUT STRICT JSON ONLY:

{{
  "page_type": "",
  "keep": true,
  "confidence": 0.0,
  "summary": {{
    "name": "",
    "description": "",
    "pricing_note": ""
  }}
}}

RULES:
- confidence must be between 0 and 1
- pricing_note should be "custom quote" if no price is shown
- DO NOT include explanations
"""

        response = self.model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "response_mime_type": "application/json"
            }
        )

        try:
            data = json.loads(response.text)

            return PageDecision(
                url=url,
                page_type=data.get("page_type", "INFO"),
                confidence=float(data.get("confidence", 0.0)),
                summary=data.get("summary", {})
            )

        except Exception:
            return None
