# Product Catalog Web Scraper

A powerful web scraping system that intelligently extracts structured product data from e-commerce websites using static HTML parsing.

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run scraper
python run.py --url https://example.com/products

# API Server
uvicorn app:app --host 0.0.0.0 --port 7860

# Web Interface
streamlit run streamlit_app.py
```

## 📋 Features

### Model S (Static) - Default
- ⚡ **Fast** HTML scraping with Jina
- 📄 Standard product pages
- 🚫 No JavaScript execution
- 💾 Low memory usage
- 🎯 Smart page classification

### Model LAM (Large Action Model) - Advanced
- 🤖 **Gemini AI** powered extraction
- 🌐 Browser automation (Playwright)
- ⚙️ Interactive configurators
- 🎯 Smart decision making
- 🔄 Automatic fallback to static

### Common Features
- **Smart classification**: Automatic page type detection  
- **Multiple export formats**: JSON, CSV, Google Sheets, Quotations
- **Configurator detection**: Identifies customizable products
- **External scraper support**: Handles iframe/embedded configurators
- **Flexible strictness**: Lenient, balanced, or strict classification

## 🛠️ Installation

```bash
# Clone and setup
git clone <repo-url>
cd product-catalogue-ai
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install
pip install -r requirements.txt

# Configure (optional)
cp .env.example .env
# Edit .env with your API keys
```

## 📚 Usage

### CLI

```bash
# Basic usage (Model S - Static)
python run.py --url https://example.com --max-pages 50 --export json,csv

# Use Model LAM (Gemini-powered)
python run.py --url https://example.com --model LAM --max-pages 20

# Full options
python run.py \
  --url https://example.com/products \
  --model LAM \
  --max-pages 50 \
  --strictness balanced \
  --export json,csv,quotation

# Available options
--model {S,LAM}                    # S=Static (default), LAM=Gemini-enhanced
--strictness {lenient,balanced,strict}
--max-pages N                      # Max pages to crawl
--max-depth N                      # Max crawl depth
--delay SECONDS                    # Delay between requests
--export FORMATS                   # json,csv,csv_prices,quotation
```

##Start server
uvicorn app:app --port 7860

# Scrape
curl -X POST http://localhost:7860/scrape -H "Content-Type: application/json" -d '{
  "url": "https://example.com",
  "strictness": "balanced",
  "export_formats": ["json"]
}'
```

# Model D only  
POST /scrape/dynamic

# Check status
GET /jobs/{job_id}

# Download
GET /download/{job_id}/json
```

### Python

```python
from src.core.balanced_scraper import BalancedScraper
from src.core.config import ScraperConfig

# Model S (Static)
from src.core.balanced_scraper import BalancedScraper
from src.core.config import ScraperConfig

config = ScraperConfig(base_url="https://example.com")
scraper = BalancedScraper(config, strictness="balanced")
catalog = scraper.scrape_all_products()

# Model LAM (Gemini-enhanced)
from src.core.lam_scraper import LAMScraper

config = ScraperConfig(base_url="https://example.com")
scraper = LAMScraper(
    config,
    strictness="balanced",
    enable_gemini=True

## 📊 Architecture

```
CLI / API / Frontend
        ↓
   Balanced Scraper
   (Static Parsing)
        ↓
  Classification
        ↓
   Extraction
        ↓
  Export & Storage
```

## 📁 Key Files

- `run.py` - CLI entry point
- `app.py` - FastAPI backend
- `streamlit_app.py` - Web interface
- `src/core/balanced_scraper.py` - Main scraper
- `src/classifiers/` - Page classification
- `src/extractors/` - Data extraction

## 🔧 Configuration

Create `.env`:
```bash
JINA_API_KEY=your_key          # Required for all models
GEMINI_API_KEY=your_key        # Required for Model LAM
GOOGLE_CREDENTIALS_FILE=...    # Optional for Google Sheets export
GOOGLE_SPREADSHEET_ID=...      # Optional for Google Sheets export
```

## 🤖 Models

### Model S (Static)
- Fast HTML scraping with Jina
- No browser automation
- Best for standard e-commerce sites
- Low resource usage

### Model LAM (Large Action Model)
- Gemini AI powered extraction
- Intelligent configurator detection
- Browser automation when needed
- Best for complex configurators
- Automatic fallback to static

**See [readmes/MODEL_LAM.md](readmes/MODEL_LAM.md) for detailed LAM documentation.**

## 🐛 Troubleshooting

**"Gemini not enabled"** (Model LAM)
```bash
# Set API key in environment
export GEMINI_API_KEY=your_key_here
```

**"LAM model not available"**
```bash
pip install google-generativeai playwright
playwright install chromium
```

**"No products found"**
- Try `--strictness lenient`
- Increase `--max-pages`
- Check if site requires JavaScript (use `--model LAM`)

**"Configurator confidence too low"**
- Re[README.md](README.md)** (this file) - Quick start and overview
- **[readmes/MODEL_LAM.md](readmes/MODEL_LAM.md)** - Model LAM detailed guide
- **[readmes/USAGE_GUIDE.md](readmes/USAGE_GUIDE.md)** - Detailed usage examples
- **[CLEANUP_SUMMARY.md](CLEANUP_SUMMARY.md)** - Architecture details
- **[tests/MODEL_D_REMOVAL_SUMMARY.md](tests/MODEL_D_REMOVAL_SUMMARY.md)** - Model D removal notes
- **/docs** (when API running) - Interactive API documentation

## 🎓 Examples

### Model S (Static) - Fast extraction
```bash
python run.py --url https://example.com/products --max-pages 50
```

### Model LAM - Complex configurators
```bash
python run.py --url https://example.com/configure --model LAM --max-pages 20
```

### Export to Google Sheets
```bash
python run.py --url https://example.com --export google_sheets
```

See complete examples in [readmes/USjob |
| `/jobs/{id}` | GET | Get job status |
| `/download/{id}/{format}` | GET | Download results |
| `/info` | GET | System capabilities |
| `/health` | GET | Health check |

## 🚀 Features

✅ Multiple scraping models (S, LAM)
✅ Smart model selection
✅ Gemini AI integration (LAM)
✅ Browser automation when needed (LAM)
✅ Multiple export formats
✅ Google Sheets integration
✅ Background job processing
✅ Progress tracking
✅ Configurator detection
✅ External configurator support
✅ Price extraction
✅ Customization options extraction

## 📝 Version

**Version:** 4.0.0
**Updated:** February 2, 2026
**Models:** S (Static), LAM (Large Action Model with Gemini
✅ Progress tracking  
✅ Configurator detection  
✅ External configurator support  
✅ Price extraction  
✅ Color/swatch detection  
✅ Customization options  

## 📝 Version

**Version:** 3.0.0  
**Updated:** February 2, 2026  
**Models:** S (Static) + D (Dynamic) + Auto (Hybrid)

## 📞 Support

- Check [USAGE_GUIDE.md](USAGE_GUIDE.md) for detailed docs
- Review Troubleshooting section
- Check `/docs` endpoint for API reference

---

**Quick Commands:**
```bash
# CLI Model S
python run.py --url https://example.com

# CLI Model D  
python run.py --model D --url https://example.com/configure

# API Server
uvicorn app:app --port 7860

# Web UI
streamlit run streamlit_app.py
```
