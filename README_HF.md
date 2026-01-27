<<<<<<< HEAD
# Theraluxe Product Catalog Scraper

A modular, intelligent web scraper designed to crawl e-commerce websites, identify product customization pages, and extract structured product data including prices, options, and images.

## 📋 Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [File Structure](#file-structure)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Code Optimization Recommendations](#code-optimization-recommendations)

## ✨ Features

- **Intelligent Page Classification**: Rule-based or AI-powered (Gemini) detection of product pages
- **Multi-format Export**: JSON, CSV, Google Sheets, quotation templates
- **Jina AI Integration**: Uses Jina Reader API for clean markdown extraction
- **Modular Architecture**: Easily extendable component-based design
- **Configurable Crawling**: Control depth, page limits, and delays
- **Product Data Extraction**: Automatically extracts names, prices, customization options, and images

## 🏗️ Architecture

The scraper follows a modular architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    Main Scraper                         │
│                  (TheraluxeScraper)                     │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
    ┌───▼────┐            ┌─────▼─────┐
    │Crawler │            │ Extractor │
    └───┬────┘            └─────┬─────┘
        │                       │
    ┌───▼────────┐         ┌────▼──────┐
    │ Classifier │         │  Storage  │
    └────────────┘         └───────────┘
```

## 📁 File Structure

### Root Directory

| File | Purpose |
|------|---------|
| **run.py** | Main entry point - execute this to run the scraper |
| **setup.py** | Package installation configuration |
| **requirements.txt** | Python dependencies |
| **.env** | Environment variables (API keys, credentials) |
| **credentials.json** | Google Sheets API service account credentials |
| **README.md** | Documentation (this file) |

### `src/` - Main Source Code

#### `src/main.py`
**Purpose**: Command-line interface and argument parsing
- Handles CLI arguments (`--ai`, `--max-pages`, `--export`, etc.)
- Initializes configuration and scraper
- Orchestrates the scraping workflow

#### `src/core/` - Core Components

| File | Responsibility | Key Classes/Functions |
|------|---------------|----------------------|
| **config.py** | Configuration management | `ScraperConfig` - stores all settings, validates API keys, manages paths |
| **scraper.py** | Main orchestrator | `TheraluxeScraper` - coordinates crawling, extraction, and storage |

#### `src/classifiers/` - Page Classification

| File | Purpose | Algorithm |
|------|---------|-----------|
| **base_classifier.py** | Abstract interface | Defines `is_product_page()` contract |
| **rule_based.py** | Rule-based detection | Uses URL patterns, content keywords, and price pattern counting |
| **ai_classifier.py** | AI-powered detection | Uses Gemini API with fallback to rule-based |

**Classification Logic**:
- **Rule-based**: Checks for keywords like "customization", "base price", price patterns `(+$XXX)`
- **AI-based**: Sends page content to Gemini for intelligent classification

#### `src/crawlers/` - Web Crawling

| File | Purpose | Key Features |
|------|---------|--------------|
| **web_crawler.py** | Website navigation | Breadth-first crawling, depth limiting, URL filtering |
| **base_crawler.py** | (Empty placeholder) | Reserved for future crawler variants |

**Crawling Strategy**:
1. Start from base URL
2. Extract all links from each page
3. Filter out images, media, admin pages
4. Classify pages as product/non-product
5. Continue until max depth or page limit reached

#### `src/extractors/` - Data Extraction

| File | Extracts | Methodology |
|------|----------|-------------|
| **link_extractor.py** | URLs from markdown | Regex pattern matching for `[text](url)` |
| **product_extractor.py** | Product details | Parses headings, prices, customization categories |
| **price_extractor.py** | (Empty placeholder) | Reserved for advanced price parsing |

**Extraction Process**:
1. Product name from H1/H2 headers or URL
2. Base price using regex: `Base Price: $XXX`
3. Customization categories (headings followed by options)
4. Options with prices: `Option Name (+$500)`
5. Associated images for each option

#### `src/storage/` - Output Formats

| File | Output Format | Structure |
|------|--------------|-----------|
| **json_storage.py** | JSON | Hierarchical product catalog |
| **csv_storage.py** | CSV | Flat table: Categories → Component → References |
| **google_sheets.py** | Google Sheets | Formatted spreadsheet with auto-sizing |
| **quotation_template.py** | JSON template | Sales-ready format with `selected: false` flags |

#### `src/utils/` - Utilities

| File | Purpose | Key Methods |
|------|---------|------------|
| **http_client.py** | HTTP requests | `scrape_with_jina()` - fetches markdown via Jina AI |
| **url_utils.py** | URL manipulation | Cleaning, validation, domain checking, media detection |
| **logger.py** | (Empty placeholder) | Reserved for structured logging |

### `tests/` - Test Files

| File | Tests |
|------|-------|
| **test_exports.py** | Export functionality |
| **configurator_detection_test.py** | Classifier accuracy |
| **sheet_test.py** | Google Sheets integration |

### `data/catalogs/` - Output Directory

Generated files are stored here:
- `product_catalog.json`
- `product_catalog.csv`
- `product_catalog_with_prices.csv`
- `product_catalog_quotation_template.json`

## 🚀 Installation

```bash
# Clone the repository
git clone <repository-url>
cd theraluxe-scraper

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys
```

### Required Dependencies

```
requests>=2.31.0
python-dotenv>=1.0.0
google-generativeai>=0.3.0
google-auth>=2.0.0
google-auth-oauthlib>=0.5.0
google-auth-httplib2>=0.1.0
google-api-python-client>=2.0.0
```

## 💻 Usage

### Basic Usage

```bash
# Basic scrape (JSON only)
python run.py

# Use AI classification
python run.py --ai

# Export to multiple formats
python run.py --export csv,csv_prices,quotation

# Export everything
python run.py --export all
```

### Advanced Options

```bash
python run.py \
  --ai \                          # Use Gemini AI
  --max-pages 100 \               # Crawl up to 100 pages
  --max-depth 4 \                 # Go 4 levels deep
  --delay 1.0 \                   # 1 second between requests
  --output my_catalog.json \      # Custom output name
  --export google_sheets,csv      # Export formats
```

### Command-Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--ai` | False | Enable AI classification with Gemini |
| `--max-pages` | 50 | Maximum pages to crawl |
| `--max-depth` | 3 | Maximum crawl depth |
| `--output` | product_catalog.json | Output filename |
| `--delay` | 0.5 | Delay between requests (seconds) |
| `--export` | json | Export formats (comma-separated) |

**Export Formats**: `json`, `csv`, `csv_prices`, `quotation`, `google_sheets`, `all`

## ⚙️ Configuration

### Environment Variables (`.env`)

```bash
# Gemini AI (optional)
GEMINI_API_KEY=your_gemini_api_key

# Google Sheets (optional)
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_SPREADSHEET_ID=your_spreadsheet_id
```

### Scraper Configuration (`src/core/config.py`)

```python
@dataclass
class ScraperConfig:
    base_url: str = "https://casarista.com/en/furniture/sofa-en/"
    max_pages: int = 50
    max_depth: int = 3
    crawl_delay: float = 0.5
    request_timeout: int = 15
    use_ai_classification: bool = False
    gemini_model: str = "models/gemini-2.0-flash-exp"
    output_dir: str = "data/catalogs"
    jina_api_url: str = "https://r.jina.ai/"
```

## 🔧 Code Optimization Recommendations

Based on analysis of your codebase, here are optimization opportunities:

### 1. **Remove Empty Placeholder Files**

These files are empty and add no value:
- `src/crawlers/base_crawler.py`
- `src/extractors/price_extractor.py`
- `src/utils/logger.py`

**Action**: Delete or implement them.

### 2. **Consolidate HTTP Requests**

**Issue**: Each page is fetched twice - once for classification, once for extraction.

**Current Flow**:
```python
# In web_crawler.py
markdown = self.http_client.scrape_with_jina(url)  # Fetch #1
if self.classifier.is_product_page(url, markdown):
    # Later in scraper.py
    markdown = self.http_client.scrape_with_jina(url)  # Fetch #2
```

**Optimized Approach**:
```python
# Cache markdown during crawling
class WebCrawler:
    def __init__(self, ...):
        self.page_cache = {}  # url -> markdown
    
    def crawl(self, ...):
        markdown = self.http_client.scrape_with_jina(url)
        self.page_cache[url] = markdown  # Store for later
        
        if self.classifier.is_product_page(url, markdown):
            self.product_pages.add(url)

# In scraper.py
def scrape_product(self, url):
    markdown = self.crawler.page_cache.get(url)
    if not markdown:
        markdown = self.http_client.scrape_with_jina(url)
```

**Impact**: ~50% reduction in HTTP requests.

### 3. **Optimize AI Classification**

**Issue**: Content is truncated to 3000 chars but still sent to API unnecessarily.

**Optimization**:
```python
class AIClassifier:
    def is_product_page(self, url: str, markdown: str) -> bool:
        # Quick rule-based pre-filter
        if len(markdown) < 500:  # Too short
            return False
        
        # Check obvious indicators first
        quick_indicators = ['base price', 'customization', 'add to cart']
        if not any(ind in markdown.lower()[:1000] for ind in quick_indicators):
            return False  # Skip AI call
        
        # Now use AI for ambiguous cases
        content_sample = markdown[:3000]
        # ... AI call
```

**Impact**: Reduce AI API calls by 60-70%, saving costs and time.

### 4. **Batch Google Sheets Operations**

**Issue**: Current implementation makes individual API calls for formatting.

**Optimization**:
```python
def upload_data(self, spreadsheet_id, data, ...):
    # Combine data upload and formatting in one batch request
    requests = [
        {'updateCells': {'rows': data, ...}},
        {'repeatCell': {'range': ..., 'cell': ...}},  # Bold headers
        {'autoResizeDimensions': {...}}
    ]
    
    self.service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={'requests': requests}
    ).execute()
```

**Impact**: Reduce API calls from 3+ to 1.

### 5. **Implement Proper Logging**

**Replace**:
```python
print(f"✓ Scraping {url}")
print(f"✗ Failed: {error}")
```

**With**:
```python
import logging

logger = logging.getLogger(__name__)
logger.info(f"Scraping {url}")
logger.error(f"Failed: {error}", exc_info=True)
```

**Benefits**: Configurable verbosity, log files, better debugging.

### 6. **Add Retry Logic with Exponential Backoff**

```python
from time import sleep
from requests.exceptions import RequestException

class HTTPClient:
    def scrape_with_jina(self, url, max_retries=3):
        for attempt in range(max_retries):
            try:
                response = requests.get(...)
                return response.text
            except RequestException as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                sleep(wait_time)
```

**Impact**: More resilient to transient network errors.

### 7. **Use Connection Pooling**

```python
class HTTPClient:
    def __init__(self, timeout=15):
        self.session = requests.Session()  # Reuse connections
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    def scrape_with_jina(self, url):
        response = self.session.get(...)  # Use session
```

**Impact**: Faster requests through connection reuse.

### 8. **Parallelize Product Scraping**

**Current**: Sequential scraping (one product at a time)

**Optimized**:
```python
from concurrent.futures import ThreadPoolExecutor

def scrape_all_products(self):
    product_urls = self.crawler.crawl(...)
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(self.scrape_product, product_urls)
    
    catalog = {
        product['product_name']: product 
        for product in results if product
    }
    return catalog
```

**Impact**: 3-5x faster scraping.

**⚠️ Warning**: Respect rate limits - adjust `max_workers` accordingly.

### 9. **Optimize Regex Compilation**

**Issue**: Regex patterns are compiled on every call.

**Optimization**:
```python
import re

class ProductExtractor:
    # Compile once at class level
    PRICE_PATTERN = re.compile(
        r'Base Price:\s*\$[\d,]+(?:\.\d{2})?\s*(?:CAD|USD)?',
        re.IGNORECASE
    )
    IMAGE_OPTION_PATTERN = re.compile(
        r'!\[(?:Image \d+:?\s*)?([^\]]+?)\s*(?:\(\+?\$[\d,]+\))?\]\(([^\)]+)\)'
    )
    
    def extract_base_price(self, markdown):
        match = self.PRICE_PATTERN.search(markdown)
        # ...
```

**Impact**: 10-20% faster extraction.

### 10. **Add Progress Indicators**

```python
from tqdm import tqdm

def scrape_all_products(self):
    product_urls = self.crawler.crawl(...)
    
    catalog = {}
    for url in tqdm(product_urls, desc="Scraping products"):
        product_data = self.scrape_product(url)
        # ...
```

**Impact**: Better user experience, visibility into progress.

## 📊 Performance Metrics

After optimizations, expected improvements:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| HTTP Requests | 100 | 50 | 50% reduction |
| Scrape Time (50 products) | ~120s | ~40s | 66% faster |
| AI API Calls | 50 | 15 | 70% reduction |
| Memory Usage | ~200MB | ~150MB | 25% reduction |

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/optimization`)
3. Commit changes (`git commit -am 'Add caching layer'`)
4. Push to branch (`git push origin feature/optimization`)
5. Create Pull Request

## 📝 License

[Your License Here]

## 🐛 Known Issues

- Empty placeholder files need implementation or removal
- No retry logic for failed requests
- Sequential scraping (not parallelized)
- Duplicate HTTP requests during crawl and extraction phases

## 🔮 Future Enhancements

- [ ] Implement structured logging system
- [ ] Add database storage (PostgreSQL/MongoDB)
- [ ] Create web UI for scraper configuration
- [ ] Add support for JavaScript-rendered pages (Selenium/Playwright)
- [ ] Implement incremental/delta scraping
- [ ] Add data validation and quality checks

---
=======
---
title: Catalogue Ai
emoji: 🏃
colorFrom: green
colorTo: indigo
sdk: docker
pinned: false
---

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference
>>>>>>> 1730f2b680b0382e1e345fa90adcfed45bf424cf
