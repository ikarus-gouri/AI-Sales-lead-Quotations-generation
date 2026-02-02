# Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│                    (CLI Entry Point)                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ├─→ Parse CLI Arguments
                       ├─→ Create ScraperConfig
                       ├─→ Select Model (S or D)
                       │
            ┌──────────┴──────────┐
            │                     │
    ┌───────▼────────┐   ┌───────▼────────┐
    │ Model-S        │   │ Model-D        │
    │ BalancedScraper│   │ DynamicScraper │
    └───────┬────────┘   └───────┬────────┘
            │                     │
            │                     ├─→ DynamicClassifier
            │                     │   (Routes to S or D per page)
            │                     │
    ┌───────▼─────────────────────▼────────┐
    │          WebCrawler                   │
    │   (Page Discovery + Classification)   │
    └──────────────┬────────────────────────┘
                   │
                   ├─→ Link Extraction
                   ├─→ Page Classification
                   └─→ Product Page Collection
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼────────┐   ┌────────▼─────────┐
│ Static Extract │   │ Dynamic Extract  │
│ (Model-S)      │   │ (Model-D)        │
├────────────────┤   ├──────────────────┤
│• Jina AI MD   │   │• Playwright      │
│• Pattern Match │   │• Browser Auto    │
│• External URL  │   │• Control Detect  │
└───────┬────────┘   └────────┬─────────┘
        │                     │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │   Product Catalog   │
        │   (Unified Format)  │
        └──────────┬──────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
   ┌────▼────┐           ┌───▼────┐
   │ JSON    │           │ CSV    │
   │ Storage │           │ Storage│
   └─────────┘           └────────┘
```

## Component Flow

### 1. Entry Point (main.py)
- Parses command-line arguments
- Creates `ScraperConfig` with settings
- Selects scraper based on `--model` flag:
  - `S` → `BalancedScraper` (Model-S only)
  - `D` or `auto` → `DynamicScraper` (Hybrid S/D)

### 2. Scraper Initialization

#### Model-S (BalancedScraper)
```python
BalancedScraper
├── BalancedClassifier (static classification)
├── WebCrawler (page discovery)
├── ProductExtractor (data extraction)
├── ConfiguratorDetector (configurator detection)
└── Storage (JSON, CSV, Google Sheets)
```

#### Model-D (DynamicScraper)
```python
DynamicScraper
├── DynamicClassifier (hybrid routing)
│   ├── BalancedClassifier (static classification)
│   └── DynamicConfiguratorDetector (JS detection)
├── WebCrawler (page discovery with routing)
├── BrowserRunner (Playwright automation)
│   ├── OptionDiscovery (control detection)
│   ├── NetworkCapture (API monitoring)
│   └── PriceLearner (pricing analysis)
└── Storage (JSON, CSV, Google Sheets)
```

### 3. Page Classification

```
Page URL + Content
    │
    ▼
┌─────────────────┐
│ URL Analysis    │
│ - Product words │
│ - SKU patterns  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Content Signals │
│ - Price count   │
│ - Keywords      │
│ - Structure     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Score Calc      │
│ Total >= 5.0?   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
   YES       NO
    │         │
PRODUCT    OTHER
```

### 4. Dynamic Detection (Model-D Only)

```
Product Page Detected
    │
    ▼
┌──────────────────────┐
│ Check Signals        │
│ ├─ JS Framework?     │
│ ├─ SPA Patterns?     │
│ ├─ Dynamic Pricing?  │
│ ├─ Price + No Options│
│ └─ Known Platform?   │
└──────────┬───────────┘
           │
    ┌──────┴──────┐
    │ Calculate   │
    │ Confidence  │
    └──────┬──────┘
           │
      ┌────┴────┐
      │         │
   >= 50%    < 50%
      │         │
  Model-D   Model-S
  (Browser) (Static)
```

### 5. Extraction Methods

#### Static Extraction (Model-S)
```
1. Fetch page (Jina AI → Markdown)
2. Extract product name from headers
3. Extract base price
4. Detect configurator:
   - External URL? → Follow & scrape
   - Embedded? → Extract from page
   - None? → Extract from markdown
5. Parse customizations:
   - Categories (Size:, Color:, etc.)
   - Options (images, checkboxes, bullets)
   - Prices (+$50, etc.)
6. Build product data dictionary
```

#### Dynamic Extraction (Model-D)
```
1. Initialize Playwright browser
2. Navigate to page (wait: domcontentloaded)
3. Wait for dynamic content (2 seconds)
4. Discover interactive controls:
   - Dropdowns (select, custom)
   - Radio buttons
   - Checkboxes
   - Input fields
   - Buttons
5. Monitor network activity:
   - API calls
   - Price updates
   - Configuration requests
6. Learn pricing model:
   - Base price
   - Price deltas per option
   - Dependencies
7. Build product data dictionary
```

## Key Algorithms

### Static Classification Algorithm
```python
def classify_product_page(url, markdown):
    score = 0.0
    
    # URL signals (0-2 points)
    if has_product_keywords(url):
        score += 1.0
    if has_sku_pattern(url):
        score += 1.0
    
    # Content signals (0-6.5 points)
    product_keywords = count_keywords(markdown, PRODUCT_KEYWORDS)
    score += min(product_keywords, 5) * 0.5
    
    customization_keywords = count_keywords(markdown, CUSTOMIZATION_KEYWORDS)
    score += min(customization_keywords, 5) * 0.5
    
    # Price signals (0-2.5 points)
    price_count = count_prices(markdown)
    if price_count > 0:
        score += 1.0
        if price_count > 5:
            score += 0.5
        if has_price_variants(markdown):
            score += 1.0
    
    # Structure signals (0-3 points)
    option_categories = count_option_categories(markdown)
    score += min(option_categories, 3) * 1.0
    
    # CTA signals (0-1 point)
    if has_cta_buttons(markdown):
        score += 1.0
    
    # Negative signals
    blog_indicators = count_blog_patterns(markdown)
    score -= min(blog_indicators, 2) * 1.0
    
    # Decision
    threshold = {
        "strict": 7.0,
        "balanced": 5.0,
        "lenient": 3.0
    }
    
    return score >= threshold[strictness]
```

### Dynamic Detection Algorithm
```python
def detect_dynamic_configurator(url, markdown):
    confidence = 0.0
    reasons = []
    
    # Framework detection (+25%)
    if detect_js_framework(markdown):
        confidence += 0.25
        reasons.append("js_framework")
    
    # SPA patterns (+20%)
    if detect_spa_pattern(markdown):
        confidence += 0.20
        reasons.append("spa_detected")
    
    # Dynamic pricing (+25%)
    if detect_dynamic_pricing(markdown):
        confidence += 0.25
        reasons.append("dynamic_pricing")
    
    # Critical signal (+50%)
    has_price = detect_price_element(markdown)
    has_options = detect_static_options(markdown)
    if has_price and not has_options:
        confidence += 0.50
        reasons.append("price_without_static_options")
    
    # Known platform (+15%)
    if detect_known_platform(url, markdown):
        confidence += 0.15
        reasons.append("known_platform")
    
    # Decision
    return {
        "is_dynamic": confidence >= 0.50,
        "confidence": confidence,
        "reasons": reasons
    }
```

## Data Structures

### Product Data (Unified Format)
```python
{
    "product_name": str,
    "url": str,
    "base_price": str | None,
    "model": "S" | "D",
    "extraction_method": "static" | "dynamic_browser",
    
    # Configurator metadata
    "has_configurator": bool,
    "configurator_type": "embedded" | "external" | "dynamic" | None,
    "configurator_url": str | None,
    "configurator_confidence": float,
    
    # Customization data
    "customization_source": str,
    "customization_categories": List[str],
    "customizations": {
        "Category Name": [
            {
                "label": str,
                "price": str | None,
                "image": str | None
            }
        ]
    },
    "total_customization_options": int,
    
    # Classification metadata
    "classification": {
        "page_type": str,
        "is_product": bool,
        "confidence": float,
        "model": "S" | "D",
        ...
    }
}
```

## Performance Characteristics

| Aspect | Model-S | Model-D |
|--------|---------|---------|
| **Speed** | ⚡ Fast (1-2s per page) | 🐢 Slow (10-30s per page) |
| **Accuracy** | Good for static pages | Excellent for JS pages |
| **Resource Usage** | Low (HTTP only) | High (browser + HTTP) |
| **JavaScript Support** | ❌ No | ✅ Yes |
| **Dynamic Content** | ❌ Limited | ✅ Full support |
| **Reliability** | High (simple) | Medium (complex) |
| **Fallback** | None | Falls back to Model-S |

## Design Patterns

### 1. Strategy Pattern
- Different extraction strategies (static vs dynamic)
- Interchangeable at runtime
- Common interface (`scrape_product()`)

### 2. Factory Pattern
- Scraper creation based on model selection
- Configuration-driven instantiation

### 3. Facade Pattern
- Simplified interfaces for complex subsystems
- `BalancedScraper` and `DynamicScraper` hide complexity

### 4. Observer Pattern
- Network activity monitoring in Model-D
- Event-driven price learning

### 5. Template Method Pattern
- Common scraping workflow
- Subclasses override specific steps

## Extension Points

### Adding New Classifiers
1. Inherit from `BaseClassifier`
2. Implement `is_product_page()` method
3. Add scoring logic

### Adding New Extractors
1. Create extractor in `src/extractors/`
2. Add to `ProductExtractor` composition
3. Call from `extract_customizations()`

### Adding Export Formats
1. Create storage handler in `src/storage/`
2. Implement `save()` method
3. Add to `save_catalog()` routing

### Adding Detection Signals
1. Add pattern to `DynamicConfiguratorDetector`
2. Update `_calculate_dynamic_confidence()`
3. Document weight in README

## Testing Strategy

```bash
# Test static extraction
python main.py --url <static-page> --model S

# Test dynamic detection
python main.py --url <js-configurator> --model D

# Test hybrid routing
python main.py --url <mixed-site> --model D

# Test with different strictness
python main.py --url <site> --strictness lenient
python main.py --url <site> --strictness balanced
python main.py --url <site> --strictness strict

# Verify no browser fallback
python main.py --url <site> --model D --no-headless
```

## Error Handling

```
Error Type → Handling Strategy
├─ Network Error → Retry with exponential backoff
├─ Browser Timeout → Fallback to Model-S
├─ Classification Error → Log and skip page
├─ Extraction Error → Return partial data
└─ Storage Error → Log and continue
```

## Future Enhancements

1. **AI-Powered Classification**
   - Use Gemini API for intelligent page classification
   - Already scaffolded in code

2. **Parallel Crawling**
   - Async HTTP requests
   - Concurrent browser sessions

3. **Caching Layer**
   - Cache markdown conversions
   - Cache classification results

4. **Smart Retry Logic**
   - Exponential backoff
   - Circuit breaker pattern

5. **Advanced Option Discovery**
   - Computer vision for color swatches
   - NLP for option label parsing
   - Machine learning for control detection
