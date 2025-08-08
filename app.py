import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import json
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from typing import List, Dict, Optional

# Page configuration
st.set_page_config(
    page_title="Target Product Scraper",
    page_icon="🎯",
    layout="wide"
)

class TargetScraper:
    def __init__(self):
        self.session = requests.Session()
        # Use headers that mimic a real browser more closely
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })
    
    def try_api_approach(self, search_term: str, offset: int = 0) -> List[Dict]:
        """Try to use Target's internal API endpoints"""
        # Target's search API endpoint (reverse engineered)
        api_urls = [
            f"https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2?key=9f36aeafbe60771e321a7cc95a78140772ab3e96&channel=WEB&count=24&default_purchasability_filter=true&include_sponsored=true&keyword={search_term}&offset={offset}&platform=desktop&pricing_store_id=3991&useragent=Mozilla/5.0%20(Windows%20NT%2010.0;%20Win64;%20x64)%20AppleWebKit/537.36%20(KHTML,%20like%20Gecko)%20Chrome/120.0.0.0%20Safari/537.36&visitor_id=0181C4C6A8C902019A8A4B62F5BC68F7",
            f"https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v1?key=9f36aeafbe60771e321a7cc95a78140772ab3e96&channel=WEB&count=24&keyword={search_term}&offset={offset}",
        ]
        
        for api_url in api_urls:
            try:
                response = self.session.get(api_url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    return self.parse_api_response(data)
            except Exception as e:
                continue
        
        return []
    
    def parse_api_response(self, data: dict) -> List[Dict]:
        """Parse Target API response"""
        products = []
        
        try:
            # Navigate the API response structure
            search_response = data.get('data', {}).get('search', {})
            products_data = search_response.get('products', [])
            
            for item in products_data:
                product = {
                    'tcin': item.get('tcin'),
                    'title': item.get('item', {}).get('product_description', {}).get('title'),
                    'image': None,
                    'rating': None,
                    'review_count': None,
                    'price': None,
                    'is_sponsored': item.get('is_sponsored', False)
                }
                
                # Extract image
                enrichment = item.get('item', {}).get('enrichment', {})
                images = enrichment.get('images', {})
                if images.get('primary_image_url'):
                    product['image'] = images['primary_image_url']
                
                # Extract rating and reviews
                guest_reviews = item.get('item', {}).get('guest_reviews', {})
                if guest_reviews.get('average_rating'):
                    product['rating'] = float(guest_reviews['average_rating'])
                if guest_reviews.get('count'):
                    product['review_count'] = int(guest_reviews['count'])
                
                # Extract price
                price_info = item.get('price', {})
                if price_info.get('formatted_current_price'):
                    product['price'] = price_info['formatted_current_price']
                elif price_info.get('current_retail'):
                    product['price'] = f"${price_info['current_retail']}"
                
                if product['tcin']:  # Only add if we have a TCIN
                    products.append(product)
        
        except Exception as e:
            st.warning(f"Error parsing API response: {str(e)}")
        
        return products
    
    def extract_search_term_from_url(self, url: str) -> Optional[str]:
        """Extract search term from Target URL"""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # Try different parameter names
        for param in ['searchTerm', 'Ntt', 'q']:
            if param in query_params:
                return query_params[param][0].replace('+', ' ')
        
        # Try to extract from path
        if '/s/' in parsed.path:
            path_parts = parsed.path.split('/')
            for part in path_parts:
                if part and part != 's':
                    return part.replace('-', ' ').replace('+', ' ')
        
        return None
    
    def scrape_with_requests(self, url: str) -> List[Dict]:
        """Fallback scraping method using requests + BeautifulSoup"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            # Look for JSON-LD structured data
            soup = BeautifulSoup(response.content, 'html.parser')
            
            products = []
            
            # Try to find JSON-LD structured data
            json_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        for item in data:
                            if item.get('@type') == 'Product':
                                products.append(self.parse_structured_data(item))
                    elif data.get('@type') == 'Product':
                        products.append(self.parse_structured_data(data))
                except:
                    continue
            
            # Try to extract from window.__PRELOADED_QUERIES__ or similar
            script_tags = soup.find_all('script')
            for script in script_tags:
                if script.string and 'PRELOADED_QUERIES' in script.string:
                    try:
                        # Extract JSON data from script
                        json_match = re.search(r'window\.__PRELOADED_QUERIES__\s*=\s*({.*?});', script.string, re.DOTALL)
                        if json_match:
                            data = json.loads(json_match.group(1))
                            products.extend(self.parse_preloaded_data(data))
                    except:
                        continue
            
            return products
            
        except Exception as e:
            st.error(f"Error in requests fallback: {str(e)}")
            return []
    
    def parse_structured_data(self, data: dict) -> Dict:
        """Parse JSON-LD structured data"""
        product = {
            'tcin': None,
            'title': data.get('name'),
            'image': None,
            'rating': None,
            'review_count': None,
            'price': None,
            'is_sponsored': False
        }
        
        # Extract image
        if data.get('image'):
            if isinstance(data['image'], list):
                product['image'] = data['image'][0]
            else:
                product['image'] = data['image']
        
        # Extract rating
        if data.get('aggregateRating'):
            rating_data = data['aggregateRating']
            product['rating'] = float(rating_data.get('ratingValue', 0))
            product['review_count'] = int(rating_data.get('reviewCount', 0))
        
        # Extract price
        offers = data.get('offers', {})
        if offers.get('price'):
            product['price'] = f"${offers['price']}"
        
        # Try to extract TCIN from URL or identifier
        if data.get('url'):
            tcin_match = re.search(r'/p/[^/]+-/A-(\d+)', data['url'])
            if tcin_match:
                product['tcin'] = tcin_match.group(1)
        
        return product
    
    def parse_preloaded_data(self, data: dict) -> List[Dict]:
        """Parse preloaded query data"""
        products = []
        # This would need to be customized based on Target's actual data structure
        # which can be found by inspecting the page source
        return products
    
    def scrape_all_pages(self, start_url: str, max_pages: int = 10) -> pd.DataFrame:
        """Scrape all pages with multiple approaches"""
        all_products = []
        
        # First, try API approach if we can extract search term
        search_term = self.extract_search_term_from_url(start_url)
        
        if search_term:
            st.info(f"Attempting API approach for search term: '{search_term}'")
            
            for page in range(max_pages):
                offset = page * 24
                st.info(f"Trying API for page {page + 1} (offset: {offset})")
                
                api_products = self.try_api_approach(search_term, offset)
                
                if not api_products:
                    st.warning(f"API approach failed for page {page + 1}")
                    break
                
                all_products.extend(api_products)
                st.success(f"API Page {page + 1}: Found {len(api_products)} products")
                
                if len(api_products) < 24:  # Less than full page means we're done
                    break
                
                time.sleep(1)  # Be respectful
        
        # If API approach didn't work or found no products, try web scraping
        if not all_products:
            st.info("Falling back to web scraping approach...")
            products = self.scrape_with_requests(start_url)
            all_products.extend(products)
        
        # Convert to DataFrame
        df = pd.DataFrame(all_products)
        
        # Remove duplicates based on TCIN
        if not df.empty and 'tcin' in df.columns:
            initial_count = len(df)
            df = df.drop_duplicates(subset=['tcin'], keep='first')
            final_count = len(df)
            if initial_count != final_count:
                st.info(f"Removed {initial_count - final_count} duplicate products")
        
        return df

def main():
    st.title("🎯 Target Product Scraper (Streamlit Cloud Compatible)")
    st.markdown("Extract product information from Target.com using API and web scraping approaches")
    
    st.info("💡 **Note**: This version uses API calls and structured data parsing, which works on Streamlit Cloud without requiring browser automation.")
    
    # Sidebar configuration
    st.sidebar.header("Configuration")
    max_pages = st.sidebar.slider("Maximum pages to scrape", 1, 20, 5)
    
    # URL input
    url_input = st.text_input(
        "Enter Target.com URL:",
        placeholder="https://www.target.com/s?searchTerm=your+search+term",
        help="Enter a Target.com search results URL"
    )
    
    # Validate URL
    if url_input and not url_input.startswith('https://www.target.com'):
        st.error("Please enter a valid Target.com URL")
        return
    
    if st.button("Start Scraping", type="primary"):
        if not url_input:
            st.error("Please enter a URL")
            return
        
        # Initialize scraper
        scraper = TargetScraper()
        
        # Start scraping
        with st.spinner("Extracting product data..."):
            df = scraper.scrape_all_pages(url_input, max_pages)
        
        if df.empty:
            st.error("No products found. This could be due to:")
            st.markdown("""
            - Target's API structure has changed
            - The URL doesn't contain a valid search term
            - Rate limiting or blocking
            - The page doesn't have structured data
            """)
            
            st.markdown("**Try:**")
            st.markdown("- Using a direct search URL like: `https://www.target.com/s?searchTerm=coffee`")
            st.markdown("- Waiting a few minutes and trying again")
        else:
            st.success(f"Successfully scraped {len(df)} unique products!")
            
            # Display results
            st.subheader("Scraped Data Preview")
            st.dataframe(df, use_container_width=True)
            
            # Display statistics
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Total Products", len(df))
            with col2:
                st.metric("With Ratings", df['rating'].notna().sum())
            with col3:
                st.metric("With Reviews", df['review_count'].notna().sum())
            with col4:
                avg_rating = df['rating'].mean()
                st.metric("Avg Rating", f"{avg_rating:.2f}" if pd.notna(avg_rating) else "N/A")
            with col5:
                st.metric("With Price", df['price'].notna().sum())
            with col6:
                sponsored_count = df['is_sponsored'].sum() if 'is_sponsored' in df.columns else 0
                st.metric("Sponsored", sponsored_count)
            
            # Filter options
            st.subheader("Filter Results")
            col1, col2 = st.columns(2)
            
            with col1:
                show_sponsored = st.checkbox("Include Sponsored Products", value=True)
            with col2:
                min_rating = st.slider("Minimum Rating", 0.0, 5.0, 0.0, 0.1)
            
            # Apply filters
            filtered_df = df.copy()
            if not show_sponsored and 'is_sponsored' in df.columns:
                filtered_df = filtered_df[~filtered_df['is_sponsored']]
            if min_rating > 0:
                filtered_df = filtered_df[filtered_df['rating'] >= min_rating]
            
            if len(filtered_df) != len(df):
                st.info(f"Filtered to {len(filtered_df)} products")
                st.dataframe(filtered_df, use_container_width=True)
            
            # Download options
            st.subheader("Export Data")
            col1, col2 = st.columns(2)
            
            with col1:
                csv = filtered_df.to_csv(index=False)
                st.download_button(
                    label="📄 Download as CSV",
                    data=csv,
                    file_name="target_products.csv",
                    mime="text/csv"
                )
            
            with col2:
                # Create Excel file
                excel_buffer = pd.io.common.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    filtered_df.to_excel(writer, sheet_name='Target Products', index=False)
                excel_buffer.seek(0)
                
                st.download_button(
                    label="📊 Download as Excel",
                    data=excel_buffer.getvalue(),
                    file_name="target_products.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    # Add troubleshooting section
    with st.expander("🔧 Troubleshooting & Tips"):
        st.markdown("""
        **If you're getting no results:**
        1. Make sure you're using a search URL like: `https://www.target.com/s?searchTerm=coffee`
        2. Try different search terms
        3. Target might be blocking automated requests - try waiting and retrying
        
        **Best URL formats:**
        - Search: `https://www.target.com/s?searchTerm=your+search`
        - Category: `https://www.target.com/c/electronics`
        
        **Data Sources:**
        - Primary: Target's internal API endpoints
        - Fallback: Structured data from HTML pages
        
        **Limitations:**
        - Some dynamic content might not be captured without browser automation
        - Rate limiting may apply for large scraping jobs
        """)

if __name__ == "__main__":
    main()