"""
Gemini Flash Configurator Options Extractor
Uses Google's Gemini Flash (free tier) to extract configurator options from webpages
"""

import os
import json
import sys
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from typing import Dict, List, Optional
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class GeminiConfiguratorExtractor:
    """Extract configurator options using Gemini Flash API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini Flash with API key"""
        # Check multiple possible environment variable names
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY (or GEMINAI_API_KEY) environment variable not set")
        
        # Configure Gemini
        genai.configure(api_key=self.api_key)
        
        # Use gemini-1.5-flash (free tier)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
    def extract_page_content(self, url: str) -> Dict[str, any]:
        """Extract page content using Playwright"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            
            try:
                print(f"Loading page: {url}")
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                
                # Wait a bit for dynamic content
                page.wait_for_timeout(5000)
                
                # Extract relevant content
                content = {
                    'url': url,
                    'title': page.title(),
                    'html_snippet': page.content()[:50000],  # First 50k chars to stay within limits
                    'text_content': page.inner_text('body')[:20000],  # First 20k chars
                    'buttons': [],
                    'cards': [],
                    'forms': [],
                    'images': [],
                    'links': []
                }
                
                # Extract interactive elements
                buttons = page.query_selector_all('button, [role="button"], .btn, .button')
                content['buttons'] = [btn.inner_text()[:100] for btn in buttons[:50] if btn.inner_text()]
                
                # Extract card-like elements with images
                cards = page.query_selector_all('.card, [class*="card"], [class*="option"], [class*="choice"], [class*="model"]')
                card_data = []
                for card in cards[:30]:
                    card_info = {'text': card.inner_text()[:200] if card.inner_text() else ''}
                    img = card.query_selector('img')
                    if img:
                        card_info['image'] = img.get_attribute('src') or img.get_attribute('data-src')
                    card_data.append(card_info)
                content['cards'] = card_data
                
                # Extract all images
                images = page.query_selector_all('img')
                content['images'] = [
                    {
                        'src': img.get_attribute('src') or img.get_attribute('data-src'),
                        'alt': img.get_attribute('alt'),
                        'title': img.get_attribute('title')
                    }
                    for img in images[:50] if img.get_attribute('src') or img.get_attribute('data-src')
                ]
                
                # Extract links
                links = page.query_selector_all('a[href]')
                content['links'] = [
                    {
                        'href': link.get_attribute('href'),
                        'text': link.inner_text()[:100]
                    }
                    for link in links[:50] if link.get_attribute('href')
                ]
                
                # Extract form elements
                inputs = page.query_selector_all('input, select, textarea')
                content['forms'] = [
                    {
                        'type': inp.get_attribute('type'),
                        'name': inp.get_attribute('name'),
                        'id': inp.get_attribute('id'),
                        'placeholder': inp.get_attribute('placeholder')
                    }
                    for inp in inputs[:30]
                ]
                
                return content
                
            except Exception as e:
                print(f"Error extracting page content: {e}")
                return {'error': str(e), 'url': url}
            finally:
                browser.close()
    
    def analyze_configurator(self, page_content: Dict[str, any]) -> Dict[str, any]:
        """Use Gemini Flash to analyze configurator options"""
        
        prompt = f"""
You are a sales specialist creating a detailed sales quotation with all customizations available for the product.
Extract all configuration options from this product configurator webpage and format them for a sales quotation.

Page Title: {page_content.get('title', 'N/A')}
URL: {page_content.get('url', 'N/A')}

Buttons found: {json.dumps(page_content.get('buttons', [])[:20])}

Cards/Options found: {json.dumps(page_content.get('cards', [])[:20])}

Images found: {json.dumps(page_content.get('images', [])[:20])}

Links found: {json.dumps(page_content.get('links', [])[:20])}

Form inputs: {json.dumps(page_content.get('forms', [])[:15])}

Text content sample:
{page_content.get('text_content', '')[:5000]}

As a sales specialist, extract all customization options and organize them into a quotation format.
For each option, identify:
- Category (e.g., "Base Model", "Exterior Color", "Interior Options", "Features")
- Component name (the specific option/model name)
- Price (if mentioned, otherwise "N/A" or empty)
- References (image URLs, product page links, or related URLs)

Return your analysis as a JSON object with this structure:
{{
  "quotation": [
    {{
      "category": "string - the category name (e.g., 'Base Model(by-category)', 'Start by selecting a coach below')",
      "component": "string - the specific option/model name",
      "price": "string - price if found, otherwise 'N/A' or empty",
      "reference": "string - image URL, product page URL, or related link"
    }}
  ],
  "summary": "string - brief overview of available customizations"
}}

IMPORTANT:
- Include ALL models, options, and configurations found
- Extract image URLs (especially product images)
- Extract relevant links to product pages or model pages
- Group related items under appropriate categories
- If no price is found, use "N/A" or leave empty

Only return valid JSON, no additional text.
"""
        
        try:
            print("Analyzing with Gemini Flash...")
            response = self.model.generate_content(prompt)
            
            # Extract JSON from response
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            
            result = json.loads(response_text)
            return result
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Response text: {response.text[:500]}")
            return {
                'error': 'Failed to parse JSON response',
                'raw_response': response.text[:1000]
            }
        except Exception as e:
            print(f"Error analyzing with Gemini: {e}")
            return {'error': str(e)}
    
    def extract_configurator_options(self, url: str, save_to_file: bool = True) -> Dict[str, any]:
        """
        Main method to extract configurator options from a URL
        
        Args:
            url: The configurator URL to analyze
            save_to_file: Whether to save results to a JSON file
            
        Returns:
            Dictionary containing the extracted configurator options
        """
        print(f"\n{'='*60}")
        print(f"Gemini Flash Configurator Extractor")
        print(f"{'='*60}\n")
        
        # Step 1: Extract page content
        print("Step 1: Extracting page content...")
        page_content = self.extract_page_content(url)
        
        if 'error' in page_content:
            return page_content
        
        # Step 2: Analyze with Gemini
        print("Step 2: Analyzing with Gemini Flash...")
        configurator_data = self.analyze_configurator(page_content)
        
        # Add metadata
        result = {
            'extracted_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'url': url,
            'method': 'gemini-1.5-flash',
            'configurator': configurator_data
        }
        
        # Step 3: Save results
        if save_to_file:
            filename = f"configurator_gemini_{int(time.time())}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\n✓ Results saved to: {filename}")
        
        return result
    
    def print_summary(self, result: Dict[str, any]):
        """Print a human-readable summary of the results in sales quotation format"""
        print(f"\n{'='*80}")
        print("SALES QUOTATION - PRODUCT CUSTOMIZATION OPTIONS")
        print(f"{'='*80}\n")
        
        if 'error' in result:
            print(f"❌ Error: {result['error']}")
            return
        
        config = result.get('configurator', {})
        
        print(f"URL: {result.get('url')}")
        print(f"Extracted: {result.get('extracted_at')}\n")
        
        if config.get('summary'):
            print(f"Summary: {config['summary']}\n")
        
        # Print quotation in table format
        quotation = config.get('quotation', [])
        if quotation:
            print(f"{'='*80}")
            print(f"{'Categories':<30} {'Component':<30} {'Price':<10} {'References':<30}")
            print(f"{'='*80}")
            
            current_category = None
            for item in quotation:
                category = item.get('category', '')
                component = item.get('component', '')
                price = item.get('price', 'N/A')
                reference = item.get('reference', '')
                
                # Only print category if it's different from the previous one
                if category != current_category:
                    print(f"{category:<30} {component:<30} {price:<10} {reference}")
                    current_category = category
                else:
                    print(f"{'':<30} {component:<30} {price:<10} {reference}")
            
            print(f"{'='*80}")
            print(f"\nTotal Options Found: {len(quotation)}")
        
        print(f"\n{'='*80}\n")
    
    def export_to_csv(self, result: Dict[str, any], filename: str = None):
        """Export quotation to CSV file"""
        import csv
        
        if 'error' in result:
            print(f"Cannot export: {result['error']}")
            return
        
        config = result.get('configurator', {})
        quotation = config.get('quotation', [])
        
        if not quotation:
            print("No quotation data to export")
            return
        
        if not filename:
            filename = f"quotation_{int(time.time())}.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['Categories', 'Component', 'Price', 'References'])
            writer.writeheader()
            
            for item in quotation:
                writer.writerow({
                    'Categories': item.get('category', ''),
                    'Component': item.get('component', ''),
                    'Price': item.get('price', 'N/A'),
                    'References': item.get('reference', '')
                })
        
        print(f"✓ Quotation exported to: {filename}")
        return filename


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python gemini_configurator_extractor.py <configurator_url>")
        print("\nExample:")
        print("  python gemini_configurator_extractor.py https://www.newmarcorp.com/configure-customization/build-your-coach")
        print("\nNote: Set GEMINI_API_KEY environment variable before running")
        sys.exit(1)
    
    url = sys.argv[1]
    
    try:
        extractor = GeminiConfiguratorExtractor()
        result = extractor.extract_configurator_options(url)
        extractor.print_summary(result)
        
        # Also export to CSV
        extractor.export_to_csv(result)
        
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        print("\nTo get a free Gemini API key:")
        print("1. Visit: https://makersuite.google.com/app/apikey")
        print("2. Create an API key")
        print("3. Set it as environment variable:")
        print("   $env:GEMINI_API_KEY='your-api-key-here'")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
