---
title: Product Catalogue AI
emoji: 📈
colorFrom: red
colorTo: green
sdk: docker
pinned: false
---

# 🛍️ Product Catalogue AI

An intelligent web scraper for extracting product catalogs with customization options from e-commerce websites. Features hybrid static/dynamic extraction with automatic model selection.

## 🌟 Features

- **🎯 Dual Extraction Models**
  - **Model-S**: Fast static extraction using Jina AI markdown conversion
  - **Model-D**: Browser-based dynamic extraction for JavaScript configurators
  - **Hybrid Mode**: Automatic intelligent routing between S and D per page

- **🧠 Smart Classification**
  - Balanced classification with configurable strictness (lenient/balanced/strict)
  - Automatic detection of product pages, categories, and blog posts
  - Dynamic configurator detection for complex JavaScript-driven products

- **🎨 Advanced Customization Extraction**
  - Color extraction with HEX values from swatches and images
  - External configurator support (Shopify, WooCommerce, etc.)
  - Embedded configurator detection and navigation
  - Price variants and option discovery

- **📊 Multiple Export Formats**
  - JSON (structured catalog)
  - CSV (product list and pricing matrix)
  - Quotation templates
  - Google Sheets integration

## 🏗️ Architecture

### Core Components

```
src/
├── classifiers/          # Page classification and routing
│   ├── balanced_classifier.py    # Static page classification (Model-S)
│   ├── dynamic_classifier.py     # Hybrid routing (S/D selection)
│   └── base_classifier.py        # Base classification interface
│
├── core/                 # Main scraper engines
│   ├── balanced_scraper.py       # Model-S: Static extraction
│   ├── dynamic_scraper.py        # Model-D: Hybrid extraction
│   └── config.py                 # Configuration management
│
├── crawlers/            # Web crawling
│   └── web_crawler.py            # Page discovery with classification
│
├── dynamic/             # Browser automation (Model-D)
│   ├── browser_engine.py         # Playwright browser control
│   ├── dynamic_detector.py       # JS configurator detection
│   ├── option_discovery.py       # Interactive control detection
│   ├── network_capture.py        # API request monitoring
│   └── price_learner.py          # Dynamic pricing analysis
│
├── extractors/          # Data extraction
│   ├── product_extractor.py      # Product info extraction
│   ├── configurator_detector.py  # Configurator detection logic
│   ├── external_configurator_scraper.py  # External platforms
│   ├── color_extractor.py        # Color analysis
│   ├── color_normalizer.py       # Color name standardization
│   ├── color_sampler.py          # Image color sampling
│   ├── swatch_detector.py        # Color swatch detection
│   └── link_extractor.py         # URL discovery
│
├── storage/             # Output handlers
│   ├── json_storage.py           # JSON export
│   ├── csv_storage.py            # CSV export
│   ├── google_sheets.py          # Google Sheets integration
│   └── quotation_template.py    # Quote generation
│
└── utils/               # Utilities
    ├── http_client.py            # HTTP requests + Jina AI
    └── url_utils.py              # URL manipulation
```

### Data Flow

```
1. Entry Point (main.py)
   ↓
2. Configuration (ScraperConfig)
   ↓
3. Scraper Selection
   ├─→ Model-S (BalancedScraper)
   │   └─→ BalancedClassifier
   │
   └─→ Model-D (DynamicScraper)
       └─→ DynamicClassifier (routes to S or D per page)
   ↓
4. Web Crawler (WebCrawler)
   - Discovers pages via link extraction
   - Classifies each page (product/category/blog/other)
   - Routes to appropriate model
   ↓
5. Extraction
   ├─→ Static (ProductExtractor + ConfiguratorDetector)
   │   - Jina AI markdown conversion
   │   - Pattern-based extraction
   │   - External configurator following
   │
   └─→ Dynamic (BrowserRunner + OptionDiscovery)
       - Playwright browser automation
       - Interactive control detection
       - Network activity monitoring
       - Price learning
   ↓
6. Storage (JSONStorage, CSVStorage, etc.)
   - Multiple format export
   - Google Sheets sync
```

## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone <repo-url>
cd product-catalogue-ai

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for Model-D)
playwright install chromium
```

### Basic Usage

```bash
# Hybrid mode (recommended) - auto-selects Model-S or Model-D
python main.py --url https://example.com/products

# Static extraction only (Model-S) - fast
python main.py --url https://example.com/products --model S

# Hybrid mode (Model-D) - handles JS configurators
python main.py --url https://example.com/products --model D

# With custom settings
python main.py --url https://example.com/products \
  --strictness balanced \
  --max-pages 100 \
  --max-depth 4 \
  --export all
```

## 🎛️ Configuration

### Model Selection

| Model | Description | Use Case | Speed |
|-------|-------------|----------|-------|
| **S** | Static extraction only | Standard product pages, no JS | ⚡ Fast |
| **D** | Hybrid auto-selection | Mixed sites with JS configurators | 🐢 Slow |
| **auto** | Same as D (default) | Recommended for all sites | 🐢 Slow |

### Strictness Levels

| Level | Precision | Recall | Description |
|-------|-----------|--------|-------------|
| **lenient** | Low | High | Catches everything, some false positives |
| **balanced** | Medium | Medium | **Recommended** - good balance |
| **strict** | High | Low | Very clean results, may miss products |

### Classification Logic

**Model-S (Static Classification)**:
- URL patterns (product keywords, SKU patterns)
- Content signals (price elements, customization keywords)
- Structure analysis (option categories, checkboxes)
- CTA detection (Add to Cart, Buy Now)
- Negative signals (blog indicators, article structure)

**Model-D (Dynamic Detection)**:
- JavaScript framework detection (React, Vue, Angular)
- SPA indicators (single-page app patterns)
- Dynamic pricing signals (calculator, price-update)
- **Critical Signal**: Price present + NO static options → likely JS configurator
- Known platforms (Shopify apps, WooCommerce plugins)

**Routing Decision**:
```python
if price_found and not static_options_found:
    confidence += 0.50  # Strong signal for Model-D

if confidence >= 0.50:
    use Model-D (browser automation)
else:
    use Model-S (static extraction)
```

## 📋 Export Formats

```bash
# Single format
python main.py --url <url> --export json

# Multiple formats
python main.py --url <url> --export json,csv,quotation

# All formats
python main.py --url <url> --export all
```

**Available formats**:
- `json` - Structured catalog with full metadata
- `csv` - Product list with basic info
- `csv_prices` - Pricing matrix with variants
- `quotation` - Quote template with categories
- `google_sheets` - Direct Google Sheets sync

## 🔧 Advanced Configuration

### Environment Variables

Create a `.env` file:

```env
# Optional: Default URL
BASE_URL=https://example.com/products

# Optional: AI features (future)
GEMINI_API_KEY=your_gemini_api_key

# Optional: Google Sheets export
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_SPREADSHEET_ID=your_sheet_id
```

### Browser Settings (Model-D)

```bash
# Visible browser for debugging
python main.py --url <url> --model D --no-headless

# Adjust timeouts
# Edit src/core/dynamic_scraper.py:
self.browser_config = BrowserConfig(
    headless=True,
    timeout=60000,  # 60 seconds
    wait_after_action=1000
)
```

## 🔍 Troubleshooting

### Issue: Model-D timing out

**Solution**: Page may be too slow. Check browser settings:
```python
# In browser_engine.py, already set to "domcontentloaded"
await self.page.goto(url, wait_until="domcontentloaded")
```

### Issue: No products found

**Solutions**:
1. Try lenient mode: `--strictness lenient`
2. Increase crawl limits: `--max-pages 100 --max-depth 5`
3. Check if site blocks scrapers (add delays: `--delay 2.0`)

### Issue: Missing customization options

**Static pages (Model-S)**: Options must match patterns:
- Images with prices: `![Option (+$50)](url)`
- Checkboxes: `- [x] Option (+$50)`
- Categories: `Size:` followed by options

**Dynamic pages (Model-D)**: Browser automation finds interactive controls automatically

### Issue: Unicode errors on Windows

**Solution**: Already handled in main.py:
```python
sys.stdout.reconfigure(encoding='utf-8')
```

## 📊 Output Structure

### JSON Format

```json
{
  "product_1": {
    "product_name": "Custom Sauna",
    "url": "https://example.com/product",
    "base_price": "$1000",
    "model": "D",
    "extraction_method": "dynamic_browser",
    "has_configurator": true,
    "configurator_type": "dynamic",
    "customization_categories": ["Size", "Wood Type", "Heater"],
    "customizations": {
      "Size": [
        {"label": "6x8", "price": "+$500", "image": null}
      ]
    },
    "total_customization_options": 15
  }
}
```

## 🛠️ Development

### Adding New Extractors

1. Create extractor in `src/extractors/`
2. Import in `ProductExtractor` or `DynamicScraper`
3. Add logic to `extract_customizations()` or `_extract_dynamic()`

### Adding Export Formats

1. Create storage handler in `src/storage/`
2. Add to `save_catalog()` in scraper
3. Update CLI arguments in `main.py`

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## 📞 Support

For issues and questions, please open a GitHub issue.

---

**Built with ❤️ using Python, Playwright, and Jina AI**
