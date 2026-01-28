import streamlit as st
import time
from typing import List, Dict, Optional
import requests
import json
import pandas as pd

from src.storage.csv_storage import CSVStorage
from src.storage.json_storage import JSONStorage

# -----------------------------
# Streamlit Page Config
# -----------------------------
st.set_page_config(
    page_title="Product Catalog Scraper",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🛍️ Product Catalog Scraper")
st.markdown("Extract structured product data from e-commerce websites with real-time progress tracking.")

# -----------------------------
# Sidebar – Configuration
# -----------------------------
st.sidebar.header("⚙️ Scraper Settings")

url = st.sidebar.text_input(
    "Target Website URL",
    placeholder="https://example.com/products",
    help="Enter the full URL including https://"
)

st.sidebar.markdown("### 📊 Crawling Parameters")
max_pages = st.sidebar.slider("Max Pages", 10, 300, 50, 10)
max_depth = st.sidebar.slider("Max Crawl Depth", 1, 5, 3)
delay = st.sidebar.slider("Crawl Delay (seconds)", 0.1, 5.0, 0.5, 0.1)

st.sidebar.markdown("### 💾 Export Options")
export_formats = st.sidebar.multiselect(
    "Export Formats",
    options=["json", "csv", "csv_prices", "quotation"],
    default=["json"]
)

output_file = st.sidebar.text_input(
    "Output filename",
    value="product_catalog.json",
    help="Base filename for exports"
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📖 About")
st.sidebar.info(
    "This tool crawls e-commerce websites to extract product information "
    "including names, prices, descriptions, images, and customization options."
)

# -----------------------------
# HF API Client
# -----------------------------
HF_API_BASE = "https://gouriikarus3d-product-catalogue-ai.hf.space"

class HFAPIClient:
    """Client for interacting with HF Space backend"""
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

    def health_check(self) -> bool:
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False

    def start_scrape(self, url: str, max_pages: int, max_depth: int, 
                     crawl_delay: float, export_formats: List[str]) -> Optional[Dict]:
        try:
            payload = {
                "url": url,
                "max_pages": max_pages,
                "max_depth": max_depth,
                "crawl_delay": crawl_delay,
                "export_formats": export_formats
            }
            response = self.session.post(f"{self.base_url}/scrape", json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"❌ Error starting scrape job: {str(e)}")
            return None

    def get_job_status(self, job_id: str) -> Optional[Dict]:
        try:
            response = self.session.get(f"{self.base_url}/jobs/{job_id}", timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"❌ Error getting job status: {str(e)}")
            return None

    def download_results(self, job_id: str, format: str) -> Optional[bytes]:
        try:
            response = self.session.get(f"{self.base_url}/download/{job_id}/{format}", timeout=30)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            st.error(f"❌ Error downloading results: {str(e)}")
            return None

# -----------------------------
# HF API Scraping with Polling
# -----------------------------
def scrape_with_hf_api(api_client: HFAPIClient, url: str, max_pages: int, 
                       max_depth: int, crawl_delay: float, export_formats: List[str],
                       status_placeholder, progress_bar):
    """Run scraping job on HF API and poll for results"""
    status_placeholder.info("🚀 Submitting scraping request to HF API...")
    progress_bar.progress(5)
    
    job_response = api_client.start_scrape(url, max_pages, max_depth, crawl_delay, export_formats)
    if not job_response:
        st.error("❌ Failed to start scraping job")
        return None, None
    
    job_id = job_response.get('job_id')
    st.info(f"📋 Job ID: `{job_id}`")
    
    max_attempts = 300  # 5 minutes max
    attempt = 0
    
    stage_progress = {"pending": 10, "running": 50, "completed": 100, "failed": 0}
    
    while attempt < max_attempts:
        job_status = api_client.get_job_status(job_id)
        if not job_status:
            time.sleep(2)
            attempt += 1
            continue
        
        status = job_status.get('status', 'unknown')
        message = job_status.get('message', 'Processing...')
        progress_info = job_status.get('progress', {})
        
        stage = progress_info.get('stage', '') if progress_info else ''
        detail = progress_info.get('message', '') if progress_info else ''
        progress_pct = stage_progress.get(status, 50)
        
        status_html = f"**Status:** {status.title()}<br>**Message:** {message}"
        if stage or detail:
            status_html += f"<br>**Stage:** {stage}<br>{detail}"
        status_placeholder.markdown(status_html, unsafe_allow_html=True)
        progress_bar.progress(progress_pct)
        
        if status == 'completed':
            return job_status, job_id
        elif status == 'failed':
            st.error(f"❌ Job failed: {message}")
            return None, None
        
        time.sleep(1)
        attempt += 1
    
    st.error("⏱️ Timeout: Job took too long to complete")
    return None, None

# -----------------------------
# Main App
# -----------------------------
run_button = st.button("🚀 Start Scraping", type="primary", use_container_width=True)

if run_button:
    if not url:
        st.error("⚠️ Please enter a target URL.")
        st.stop()
    if not url.startswith(('http://', 'https://')):
        st.error("⚠️ URL must start with http:// or https://")
        st.stop()
    
    st.markdown("---")
    progress_bar = st.progress(0)
    status_placeholder = st.empty()
    metrics_placeholder = st.empty()
    
    api_client = HFAPIClient(HF_API_BASE)
    
    with st.spinner("Checking API availability..."):
        if not api_client.health_check():
            st.error(f"❌ Cannot connect to HF API at {HF_API_BASE}")
            st.stop()
    
    st.success("✅ Connected to Hugging Face API")
    
    job_result, job_id = scrape_with_hf_api(
        api_client, url, max_pages, max_depth, delay, export_formats,
        status_placeholder, progress_bar
    )
    
    if not job_result:
        st.stop()
    
    st.info("📥 Downloading results from API...")
    json_data = api_client.download_results(job_id, 'json')
    if not json_data:
        st.warning("⚠️ Could not download catalog data")
        st.json(job_result)
        st.stop()
    
    # Handle both DataFrame and list
    try:
        catalog = json.loads(json_data)
        if isinstance(catalog, list):
            preview_data = catalog[:5]
        elif isinstance(catalog, pd.DataFrame):
            preview_data = catalog.iloc[:5].to_dict(orient='records')
        else:
            preview_data = list(catalog)[:5]
    except Exception:
        preview_data = []

    st.success(f"✅ Downloaded {len(catalog)} products!")

    # -----------------------------
    # Display Results
    # -----------------------------
    st.markdown("---")
    st.subheader("📋 Results Preview")
    preview_count = len(preview_data)
    st.info(f"Showing {preview_count} of {len(catalog)} products")
    
    for i, product in enumerate(preview_data, 1):
        with st.expander(f"🛍️ Product {i}: {product.get('name', 'Unnamed Product')}", expanded=(i==1)):
            col1, col2 = st.columns([1, 3])
            with col1:
                if product.get('image_url'):
                    try: st.image(product['image_url'], use_container_width=True)
                    except: st.write("🖼️ Image unavailable")
                else: st.info("🖼️ No image")
            with col2:
                if product.get('name'): st.markdown(f"**📦 Name:** {product['name']}")
                if product.get('price'): st.markdown(f"**💰 Price:** {product['price']}")
                if product.get('sku'): st.markdown(f"**🏷️ SKU:** {product['sku']}")
                if product.get('description'): st.markdown(f"**📝 Description:** {product.get('description','')[:200]}...")
                if product.get('customization_url'): st.success("✅ Customization available")
                if product.get('url'): st.markdown(f"**🔗 URL:** [{product['url']}]({product['url']})")

    # -----------------------------
    # Downloads
    # -----------------------------
    st.markdown("---")
    st.subheader("💾 Download Results")
    cols = st.columns(len(export_formats) if export_formats else 2)
    
    for idx, format in enumerate(export_formats):
        with cols[idx]:
            if format == "json":
                st.download_button(
                    label="📥 Download JSON",
                    data=json_data,
                    file_name=output_file,
                    mime="application/json",
                    use_container_width=True
                )
            elif format == "csv":
                csv_data = CSVStorage.to_csv_string(catalog)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_data,
                    file_name=output_file.replace(".json", ".csv"),
                    mime="text/csv",
                    use_container_width=True
                )
    
    # -----------------------------
    # Statistics
    # -----------------------------
    st.markdown("---")
    st.subheader("📈 Scraping Statistics")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("📦 Total Products", len(catalog))
    with col2: st.metric("💰 With Pricing", sum(1 for p in catalog if p.get('price')))
    with col3: st.metric("🖼️ With Images", sum(1 for p in catalog if p.get('image_url')))
    with col4: st.metric("🎨 With Customization", sum(1 for p in catalog if p.get('customization_url')))
    with col5: st.metric("📝 With Description", sum(1 for p in catalog if p.get('description')))
    
    completeness = (sum(1 for p in catalog if p.get('price')) +
                    sum(1 for p in catalog if p.get('image_url')) +
                    sum(1 for p in catalog if p.get('description'))) / (len(catalog) * 3) * 100
    st.progress(int(completeness))
    st.caption(f"📊 Data completeness: {completeness:.1f}%")
