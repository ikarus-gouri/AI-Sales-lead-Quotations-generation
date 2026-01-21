# Theraluxe Product Catalog Scraper

A modular, scalable web scraper for extracting product information and customization options from the Theraluxe website.

## Features

- 🔍 **Intelligent Crawling**: Automatically discovers product pages
- 🤖 **AI Classification**: Optional AI-powered page classification using Google Gemini
- 📊 **Comprehensive Extraction**: Extracts product names, prices, and customization options
- 📁 **Multiple Export Formats**: JSON, CSV, Google Sheets, quotation templates
- 🏗️ **Modular Architecture**: Easy to extend and maintain
- 💾 **Flexible Storage**: Multiple output formats with easy expansion

## Project Structure

```
theraluxe_scraper/
├── src/
│   ├── core/              # Main scraper logic
│   ├── crawlers/          # Web crawling components
│   ├── classifiers/       # Page classification (rule-based & AI)
│   ├── extractors/        # Data extraction utilities
│   ├── storage/           # Storage backends
│   └── utils/             # Helper utilities
├── data/                  # Output directory
├── tests/                 # Unit tests
├── requirements.txt       # Dependencies
└── README.md
```

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd theraluxe_scraper
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. (Optional) Set up environment variables for AI classification:
```bash
# Create .env file
echo "GEMINI_API_KEY=your_api_key_here" > .env
```

4. (Optional) Set up Google Sheets integration:
   - See [GOOGLE_SHEETS_SETUP.md](GOOGLE_SHEETS_SETUP.md) for detailed instructions
   - Download service account credentials
   - Place `credentials.json` in project root

## Usage

### Method 1: Using run.py (Recommended for Windows)

```bash
python run.py
```

With options:
```bash
python run.py --ai --max-pages 100 --output my_catalog.json
```

### Method 2: Install as package (Recommended for development)

```bash
# Install in development mode
pip install -e .

# Then run from anywhere
theraluxe-scraper
theraluxe-scraper --ai --max-pages 100
```

### Method 3: Run as module

```bash
python -m src.main
```

### Advanced Options

```bash
# Export to multiple formats
python run.py --export json csv google_sheets

# Export everything
python run.py --export all

# AI + Google Sheets + custom settings
python run.py \
  --ai \
  --max-pages 100 \
  --max-depth 4 \
  --output my_catalog.json \
  --export all \
  --delay 1.0
```

### Export Formats

- `json` - Standard JSON catalog (default)
- `csv` - Simple CSV (Categories, Component, References)
- `csv_prices` - CSV with prices (Categories, Component, Price, References, Notes)
- `google_sheets` - Upload directly to Google Sheets
- `quotation` - JSON template for quotation system
- `all` - Export to all formats at once

### Command Line Arguments

- `--ai`: Enable AI-powered page classification
- `--max-pages N`: Maximum number of pages to crawl (default: 50)
- `--max-depth N`: Maximum crawl depth (default: 3)
- `--output FILE`: Output filename (default: product_catalog.json)
- `--export FORMAT [FORMAT ...]`: Export formats (choices: json, csv, csv_prices, google_sheets, quotation, all)
- `--delay SECONDS`: Delay between requests (default: 0.5)

## Output Format

The scraper generates a JSON file with the following structure:

```json
{
  "product_id": {
    "product_name": "Product Name",
    "url": "https://theraluxe.ca/product-page",
    "base_price": "$10,000",
    "customization_categories": ["Category 1", "Category 2"],
    "customizations": {
      "Category 1": [
        {
          "label": "Option Name",
          "price": "+$500",
          "image": "https://example.com/image.jpg"
        }
      ]
    },
    "total_customization_options": 25
  }
}
```

## Extending the Scraper

### Adding a New Classifier

Create a new classifier in `src/classifiers/`:

```python
from .base_classifier import BaseClassifier

class MyCustomClassifier(BaseClassifier):
    def is_product_page(self, url: str, markdown: str) -> bool:
        # Your classification logic
        return True
```

### Adding a New Storage Backend

Create a new storage class in `src/storage/`:

```python
class CSVStorage:
    @staticmethod
    def save(catalog: Dict, filepath: str):
        # Your CSV export logic
        pass
```

### Adding New Extractors

Create new extractors in `src/extractors/` for additional data types.

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/
```

### Type Checking

```bash
mypy src/
```

## Architecture Benefits

1. **Separation of Concerns**: Each module has a single responsibility
2. **Easy Testing**: Components are isolated and testable
3. **Scalability**: Add new features without modifying existing code
4. **Maintainability**: Clear structure makes code easy to understand
5. **Extensibility**: Simple to add new classifiers, extractors, or storage backends

## License



## Contributing

