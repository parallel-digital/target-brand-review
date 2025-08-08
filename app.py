import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import json
from urllib.parse import urljoin, urlparse, parse_qs
import io
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Target Brand Insights Scraper",
    page_icon="🎯",
    layout="wide"
)

class TargetScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        })
        self.products = []
        self.base_api_url = "https://redsky.target.com/redsky_aggregations/v1/web/"
    
    def extract_search_term_from_url(self, url):
        """Extract search term from Target search URL or convert brand URL to search term"""
        try:
            # If it's already a search URL
            if 'searchTerm=' in url:
                match = re.search(r'searchTerm=([^&]+)', url)
                return match.group(1) if match else None
            
            # If it's a brand URL, extract brand name
            elif '/b/' in url:
                # Extract brand name from URL like /b/yoobi/
                match = re.search(r'/b/([^/\-]+)', url)
                return match.group(1) if match else None
            
            return None
        except:
            return None
    
    def get_search_products_api(self, search_url, offset=0, limit=24):
        """Get products using Target's search API"""
        try:
            search_term = self.extract_search_term_from_url(search_url)
            if not search_term:
                return []
            
            # Target's search API endpoint
            api_url = f"{self.base_api_url}plp_search_v2"
            
            params = {
                'channel': 'WEB',
                'count': limit,
                'default_purchasability_filter': 'true',
                'include_sponsored': 'true',
                'keyword': search_term,
                'offset': offset,
                'platform': 'desktop',
                'pricing_store_id': '1375',
                'store_ids': '1375,2084,2715,2746',
                'useragent': 'Mozilla/5.0',
                'visitor_id': 'placeholder',
                'zip': '55403'
            }
            
            response = self.session.get(api_url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                products = []
                
                # Navigate the API response structure
                if 'data' in data and 'search' in data['data']:
                    search_data = data['data']['search']
                    if 'products' in search_data:
                        for product in search_data['products']:
                            try:
                                product_info = self.parse_api_product(product)
                                if product_info:
                                    products.append(product_info)
                            except Exception as e:
                                continue
                
                return products
            else:
                st.warning(f"API returned status code: {response.status_code}. Trying fallback method...")
                return self.fallback_search_scrape(search_term, offset, limit)
                
        except Exception as e:
            st.warning(f"API request failed: {str(e)}. Trying fallback method...")
            search_term = self.extract_search_term_from_url(search_url)
            return self.fallback_search_scrape(search_term, offset, limit) if search_term else []
    
    def fallback_search_scrape(self, search_term, offset=0, limit=24):
        """Fallback method using direct HTML scraping of search results"""
        try:
            # Construct search URL
            search_url = f"https://www.target.com/s?searchTerm={search_term}&offset={offset}"
            
            response = self.session.get(search_url, timeout=15)
            response.raise_for_status()
            
            # Look for JSON data in script tags
            soup = BeautifulSoup(response.content, 'html.parser')
            script_tags = soup.find_all('script')
            
            products = []
            for script in script_tags:
                if script.string and 'searchResponse' in script.string:
                    try:
                        # Extract JSON data from script tag
                        json_match = re.search(r'window\.__TGT_DATA__\s*=\s*({.*?});', script.string, re.DOTALL)
                        if json_match:
                            data = json.loads(json_match.group(1))
                            # Navigate to products in the data structure
                            if 'searchResponse' in data:
                                search_results = data['searchResponse']['searchResponse']['products']
                                for product in search_results:
                                    product_info = self.parse_api_product(product)
                                    if product_info:
                                        products.append(product_info)
                        break
                    except (json.JSONDecodeError, KeyError):
                        continue
            
            return products
            
        except Exception as e:
            st.error(f"Fallback scraping failed: {str(e)}")
            return []
    
    def parse_api_product(self, product_data):
        """Parse product data from Target's API response"""
        try:
            product_info = {}
            
            # Extract TCIN
            product_info['TCIN'] = product_data.get('tcin', 'N/A')
            
            # Extract title
            product_info['Title'] = product_data.get('item', {}).get('product_description', {}).get('title', 'N/A')
            
            # Extract image URL
            images = product_data.get('item', {}).get('enrichment', {}).get('images', {})
            if 'primary_image_url' in images:
                product_info['Image_URL'] = images['primary_image_url']
            elif 'alternate_image_urls' in images and images['alternate_image_urls']:
                product_info['Image_URL'] = images['alternate_image_urls'][0]
            else:
                product_info['Image_URL'] = 'N/A'
            
            # Extract price
            price_data = product_data.get('price', {})
            if 'current_retail' in price_data:
                product_info['Price'] = f"${price_data['current_retail']:.2f}"
            elif 'formatted_current_price' in price_data:
                product_info['Price'] = price_data['formatted_current_price']
            else:
                product_info['Price'] = 'N/A'
            
            # Extract ratings
            ratings_data = product_data.get('ratings_and_reviews', {})
            if 'statistics' in ratings_data:
                stats = ratings_data['statistics']
                product_info['Rating'] = stats.get('rating', {}).get('average', 'N/A')
                product_info['Review_Count'] = stats.get('rating', {}).get('count', 'N/A')
            else:
                product_info['Rating'] = 'N/A'
                product_info['Review_Count'] = 'N/A'
            
            # Create product URL
            product_info['URL'] = f"https://www.target.com/p/-/A-{product_info['TCIN']}"
            
            return product_info
            
        except Exception as e:
            return None
    
    def get_all_brand_products(self, search_url, max_pages=10):
        """Get all products from search using API pagination"""
        all_products = []
        offset = 0
        limit = 24
        
        for page in range(max_pages):
            try:
                st.info(f"Fetching page {page + 1}...")
                products = self.get_search_products_api(search_url, offset=offset, limit=limit)
                
                if not products:
                    break
                
                all_products.extend(products)
                offset += limit
                
                # If we got fewer products than the limit, we've reached the end
                if len(products) < limit:
                    break
                
                time.sleep(1)  # Be respectful
                
            except Exception as e:
                st.warning(f"Error on page {page + 1}: {str(e)}")
                break
        
        return all_products

def main():
    st.title("🎯 Target Brand Insights Scraper")
    st.markdown("Extract product details from Target.com brand pages")
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        max_pages = st.slider("Maximum pages to scrape", 1, 20, 5)
        st.info("Using Target's API for faster, more reliable data extraction")
    
    # Main interface
    st.markdown("### Enter URL or Search Term")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        input_url = st.text_input(
            "Target URL or Search Term:",
            placeholder="https://www.target.com/s?searchTerm=yoobi OR just 'yoobi'",
            help="Enter either a Target search URL or just the brand/product name"
        )
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)  # Add space
        convert_to_search = st.checkbox("Auto-convert to search", value=True, help="Automatically convert brand URLs to search URLs")
    
    # Convert input to proper search URL if needed
    if input_url:
        if input_url.startswith('http'):
            if convert_to_search and '/b/' in input_url:
                # Convert brand URL to search URL
                search_term = None
                brand_match = re.search(r'/b/([^/\-]+)', input_url)
                if brand_match:
                    search_term = brand_match.group(1)
                    search_url = f"https://www.target.com/s?searchTerm={search_term}"
                    st.info(f"🔄 Converted to search URL: {search_url}")
                else:
                    search_url = input_url
            else:
                search_url = input_url
        else:
            # Treat as search term
            search_url = f"https://www.target.com/s?searchTerm={input_url}"
            st.info(f"🔍 Using search URL: {search_url}")
    else:
        search_url = ""
    
    if st.button("Start Scraping", type="primary"):
        if not search_url:
            st.error("Please enter a URL or search term")
            return
        
        if search_url.startswith('http') and "target.com" not in search_url.lower():
            st.error("Please enter a valid Target.com URL")
            return
        
        scraper = TargetScraper()
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            # Step 1: Get all products using search API
            status_text.text("🔍 Fetching products from Target search...")
            products_data = scraper.get_all_brand_products(search_url, max_pages)
            
            if not products_data:
                st.error("No products found. This could be due to:")
                st.markdown("""
                - Invalid brand URL
                - Brand page structure changes
                - Network issues
                
                **Try these solutions:**
                1. Make sure the URL is a Target brand page (contains `/b/` and `N-`)
                2. Try a different brand page
                3. Check if the page loads correctly in your browser
                """)
                return
            
            st.success(f"Found {len(products_data)} products!")
            
            # Convert to DataFrame
            df = pd.DataFrame(products_data)
            
            st.success(f"✅ Successfully scraped {len(df)} products!")
            
            # Display data preview
            st.subheader("Data Preview")
            st.dataframe(df, use_container_width=True)
            
            # Summary statistics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Products", len(df))
            with col2:
                valid_ratings = df[df['Rating'] != 'N/A']['Rating']
                if len(valid_ratings) > 0:
                    avg_rating = pd.to_numeric(valid_ratings, errors='coerce').mean()
                    st.metric("Avg Rating", f"{avg_rating:.1f}" if not pd.isna(avg_rating) else "N/A")
                else:
                    st.metric("Avg Rating", "N/A")
            with col3:
                valid_reviews = df[df['Review_Count'] != 'N/A']['Review_Count']
                if len(valid_reviews) > 0:
                    total_reviews = pd.to_numeric(valid_reviews, errors='coerce').sum()
                    st.metric("Total Reviews", f"{int(total_reviews):,}" if not pd.isna(total_reviews) else "N/A")
                else:
                    st.metric("Total Reviews", "N/A")
            with col4:
                products_with_price = len(df[df['Price'] != 'N/A'])
                st.metric("Products with Price", products_with_price)
            
            # Download button
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"target_brand_data_{timestamp}.xlsx"
            
            # Create Excel file in memory
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Product Data', index=False)
                
                # Add a summary sheet
                summary_df = pd.DataFrame({
                    'Metric': ['Total Products', 'Products with Ratings', 'Products with Reviews', 'Products with Prices'],
                    'Count': [
                        len(df),
                        len(df[df['Rating'] != 'N/A']),
                        len(df[df['Review_Count'] != 'N/A']),
                        len(df[df['Price'] != 'N/A'])
                    ]
                })
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            output.seek(0)
            
            st.download_button(
                label="📥 Download Excel File",
                data=output,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        except Exception as e:
            st.error(f"An error occurred during scraping: {str(e)}")
        
        finally:
            progress_bar.empty()
            status_text.empty()

    # Instructions
    with st.expander("ℹ️ Instructions"):
        st.markdown("""
        **How to use this app:**
        
        1. **Enter search info**: You can use either:
           - **Search term**: Just type `yoobi` or `nike`
           - **Search URL**: `https://www.target.com/s?searchTerm=yoobi`
           - **Brand URL**: `https://www.target.com/b/yoobi/-/N-551o8` (will auto-convert)
        
        2. **Auto-conversion**: The app automatically converts brand URLs to search URLs for better results
        
        3. **Start scraping**: Click "Start Scraping" to begin data extraction
        
        4. **Download results**: Get your Excel file with all product data
        
        **Data extracted:**
        - TCIN (Target product ID)
        - Product Title
        - Image URL
        - Price/ASP
        - Rating
        - Review Count
        - Product URL
        
        **Why search URLs work better:**
        - No authentication required
        - More comprehensive results
        - Better API access
        - Handles all product variations
        """)
    
    # Disclaimer
    st.markdown("---")
    st.caption("⚠️ This tool is for educational purposes. Please respect Target.com's robots.txt and terms of service.")

if __name__ == "__main__":
    main()