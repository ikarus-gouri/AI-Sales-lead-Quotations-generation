import streamlit as st
from src.core.config import ScraperConfig
from src.core.scraper import TheraluxeScraper

st.set_page_config(
    page_title="Theraluxe Product Scraper",
    layout="wide"
)

st.title("🧖‍♀️ Theraluxe Product Catalog Scraper")
st.markdown("Scrape product catalogs from e-commerce websites.")

# -----------------------------
# Sidebar – Configuration
# -----------------------------
st.sidebar.header("Scraper Settings")

url = st.sidebar.text_input(
    "Target Website URL",
    placeholder="https://example.com"
)

use_ai = st.sidebar.checkbox(
    "Use AI Classification (Gemini)",
    value=False
)

max_pages = st.sidebar.slider(
    "Max Pages",
    min_value=10,
    max_value=300,
    value=50,
    step=10
)

max_depth = st.sidebar.slider(
    "Max Crawl Depth",
    min_value=1,
    max_value=6,
    value=3
)

delay = st.sidebar.slider(
    "Crawl Delay (seconds)",
    min_value=0.0,
    max_value=3.0,
    value=0.5,
    step=0.1
)

export_formats = st.sidebar.multiselect(
    "Export Formats",
    options=[
        "json",
        "csv",
        "csv_prices",
        "quotation",
        "google_sheets"
    ],
    default=["json"]
)

output_file = st.sidebar.text_input(
    "Output filename",
    value="product_catalog.json"
)

# -----------------------------
# Main action
# -----------------------------
run_button = st.button("🚀 Start Scraping")

# -----------------------------
# Run scraper
# -----------------------------
if run_button:
    if not url:
        st.error("Please enter a target URL.")
        st.stop()

    st.info("Initializing scraper...")

    config = ScraperConfig(
        base_url=url,
        use_ai_classification=use_ai,
        max_pages=max_pages,
        max_depth=max_depth,
        output_filename=output_file,
        crawl_delay=delay
    )

    if not config.validate():
        st.error("Configuration validation failed. Check logs.")
        st.stop()

    scraper = TheraluxeScraper(config)

    with st.spinner("Scraping in progress..."):
        catalog = scraper.scrape_all_products()

    if not catalog:
        st.warning(
            "No products found.\n\n"
            "Possible reasons:\n"
            "- Website has no product pages\n"
            "- Structure not detected correctly\n"
            "- Increase max pages / depth\n"
            "- Enable AI classification"
        )
        st.stop()

    st.success(f"✅ Found {len(catalog)} products")

    # Export
    with st.spinner("Exporting results..."):
        scraper.save_catalog(catalog, export_formats=export_formats)

    # Summary
    st.subheader("📊 Scraping Summary")
    scraper.print_summary(catalog)

    st.subheader("📁 Output Files")

    if "json" in export_formats:
        st.write(f"• JSON: `{config.full_output_path}`")

    if "csv" in export_formats:
        st.write(f"• CSV: `{config.full_output_path.replace('.json', '.csv')}`")

    if "csv_prices" in export_formats:
        st.write(
            f"• CSV (with prices): `{config.full_output_path.replace('.json', '_with_prices.csv')}`"
        )

    if "quotation" in export_formats:
        st.write(
            f"• Quotation template: `{config.full_output_path.replace('.json', '_quotation_template.json')}`"
        )

    if "google_sheets" in export_formats:
        st.write("• Google Sheets: check console output")

    st.success("🎉 Scraping completed!")
