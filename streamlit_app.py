import streamlit as st

from src.core.config import ScraperConfig
from src.core.scraper import TheraluxeScraper
from src.storage.csv_storage import CSVStorage
from src.storage.json_storage import JSONStorage


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
    options=["json", "csv"],
    default=["json"]
)

output_file = st.sidebar.text_input(
    "Output filename",
    value="product_catalog.json"
)

# -----------------------------
# Run action
# -----------------------------
run_button = st.button("🚀 Start Scraping")

if run_button:
    if not url:
        st.error("Please enter a target URL.")
        st.stop()

    config = ScraperConfig(
        base_url=url,
        use_ai_classification=use_ai,
        max_pages=max_pages,
        max_depth=max_depth,
        crawl_delay=delay,
        output_filename=output_file
    )

    if not config.validate():
        st.error("Configuration validation failed.")
        st.stop()

    scraper = TheraluxeScraper(config)

    with st.spinner("Scraping in progress..."):
        catalog = scraper.scrape_all_products()

    if not catalog:
        st.warning("No products found.")
        st.stop()

    st.success(f"✅ Found {len(catalog)} products")

    # -----------------------------
    # Downloads
    # -----------------------------
    st.subheader("📥 Download Results")

    if "json" in export_formats:
        json_data = JSONStorage.to_json_string(catalog)
        st.download_button(
            label="⬇️ Download JSON",
            data=json_data,
            file_name=output_file,
            mime="application/json"
        )

    if "csv" in export_formats:
        csv_data = CSVStorage.to_csv_string(catalog)
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_data,
            file_name=output_file.replace(".json", ".csv"),
            mime="text/csv"
        )

    st.success("🎉 Scraping completed!")
