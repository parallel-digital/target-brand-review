import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import json
from urllib.parse import urljoin, urlparse, parse_qs, quote
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
        # Use a more standard browser user agent
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })
        self.products = []
    
    def extract_product_data_from_page(self, url, search_term):
        """Extract product data directly from Target search page"""
        try:
            # Add delay to be respectful
            time.sleep(2)
            
            response = self.session.get(url, timeout=20)
            if response.status_code != 200:
                st.warning(f"Failed to fetch page: HTTP {response.status_code}")
                return []
            
            content = response.text
            products = []
            
            # Method 1: Look for JSON data in script tags
            soup = BeautifulSoup(content, 'html.parser')
            script_tags = soup.find_all('script', type='application/json')
            
            for script in script_tags:
                try:
                    if script.string:
                        data = json.loads(script.string)
                        # Look for product data in various possible structures
                        products_found = self.extract_products_from_json(data, search_term)
                        if products_found:
                            products.extend(products_found)
                            break
                except (json.JSONDecodeError, KeyError):
                    continue
            
            # Method 2: Look for inline JavaScript data
            if not products:
                script_patterns = [
                    r'window\.__TGT_DATA__\s*=\s*({.*?});',
                    r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                    r'__NEXT_DATA__\s*=\s*({.*?})'
                ]
                
                for pattern in script_patterns:
                    matches = re.findall(pattern, content, re.DOTALL)
                    for match in matches:
                        try:
                            data = json.loads(match)
                            products_found = self.extract_products_from_json(data, search_term)
                            if products_found:
                                products.extend(products_found)
                                break
                        except (json.JSONDecodeError, KeyError):
                            continue
                    if products:
                        break
            
            return products
            
        except Exception as e:
            st.error(f"Error extracting data from page: {str(e)}")
            return []
    
    def extract_products_from_json(self, data, search_term):
        """Recursively search for product data in JSON structure"""
        products = []
        
        def find_products_recursive(obj, path=""):
            if isinstance(obj, dict):
                # Look for product arrays
                for key, value in obj.items():
                    if key.lower() in ['products', 'items', 'results'] and isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict) and self.looks_like_product(item):
                                product_info = self.parse_product_json(item)
                                if product_info and self.is_relevant_product(product_info, search_term):
                                    products.append(product_info)
                    else:
                        find_products_recursive(value, f"{path}.{key}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    find_products_recursive(item, f"{path}[{i}]")
        
        find_products_recursive(data)
        return products
    
    def looks_like_product(self, item):
        """Check if a JSON object looks like a product"""
        if not isinstance(item, dict):
            return False
        
        # Check for common product fields
        product_indicators = ['tcin', 'title', 'price', 'item', 'product_description']
        return any(indicator in item for indicator in product_indicators)
    
    def is_relevant_product(self, product_info, search_term):
        """Check if product is relevant to search term"""
        if not search_term:
            return True
        
        search_term_lower = search_term.lower()
        title = product_info.get('Title', '').lower()
        
        return search_term_lower in title
    
    def parse_product_json(self, product_data):
        """Parse product data from JSON"""
        try:
            product_info = {}
            
            # Extract TCIN
            product_info['TCIN'] = str(product_data.get('tcin', product_data.get('id', 'N/A')))
            
            # Extract title - try multiple possible locations
            title_locations = [
                ['item', 'product_description', 'title'],
                ['title'],
                ['display_name'],
                ['name'],
                ['product_description', 'title']
            ]
            
            product_info['Title'] = 'N/A'
            for location in title_locations:
                value = product_data
                for key in location:
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        value = None
                        break
                if value and isinstance(value, str):
                    product_info['Title'] = value
                    break
            
            # Extract image URL
            image_locations = [
                ['item', 'enrichment', 'images', 'primary_image_url'],
                ['images', 'primary_image_url'],
                ['primary_image_url'],
                ['image_url'],
                ['item', 'enrichment', 'images', 'alternate_image_urls', 0]
            ]
            
            product_info['Image_URL'] = 'N/A'
            for location in image_locations:
                value = product_data
                for key in location:
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    elif isinstance(value, list) and isinstance(key, int) and len(value) > key:
                        value = value[key]
                    else:
                        value = None
                        break
                if value and isinstance(value, str):
                    product_info['Image_URL'] = value
                    break
            
            # Extract price
            price_locations = [
                ['price', 'current_retail'],
                ['price', 'formatted_current_price'],
                ['current_retail'],
                ['formatted_current_price'],
                ['price']
            ]
            
            product_info['Price'] = 'N/A'
            for location in price_locations:
                value = product_data
                for key in location:
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        value = None
                        break
                if value is not None:
                    if isinstance(value, (int, float)):
                        product_info['Price'] = f"${value:.2f}"
                    elif isinstance(value, str) and ('$' in value or value.replace('.', '').isdigit()):
                        product_info['Price'] = value
                    break
            
            # Extract ratings
            rating_locations = [
                ['ratings_and_reviews', 'statistics', 'rating', 'average'],
                ['rating', 'average'],
                ['average_rating'],
                ['rating']
            ]
            
            product_info['Rating'] = 'N/A'
            for location in rating_locations:
                value = product_data
                for key in location:
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        value = None
                        break
                if value is not None and isinstance(value, (int, float)):
                    product_info['Rating'] = f"{value:.1f}"
                    break
            
            # Extract review count
            review_locations = [
                ['ratings_and_reviews', 'statistics', 'rating', 'count'],
                ['rating', 'count'],
                ['review_count'],
                ['reviews']
            ]
            
            product_info['Review_Count'] = 'N/A'
            for location in review_locations:
                value = product_data
                for key in location:
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        value = None
                        break
                if value is not None and isinstance(value, (int, float)):
                    product_info['Review_Count'] = str(int(value))
                    break
            
            # Create product URL
            tcin = product_info['TCIN']
            if tcin != 'N/A':
                product_info['URL'] = f"https://www.target.com/p/-/A-{tcin}"
            else:
                product_info['URL'] = 'N/A'
            
            return product_info
            
        except Exception as e:
            return None
    
    def get_all_products(self, search_url, max_pages=5):
        """Get all products using multiple methods"""
        all_products = []
        search_term = self.extract_search_term_from_url(search_url)
        
        if not search_term:
            st.error("Could not extract search term from URL")
            return []
        
        st.info(f"Searching for: '{search_term}'")
        
        # Try different page offsets
        for page in range(max_pages):
            offset = page * 24
            page_url = f"https://www.target.com/s?searchTerm={quote(search_term)}&offset={offset}"
            
            st.info(f"Scraping page {page + 1} (offset: {offset})...")
            
            try:
                page_products = self.extract_product_data_from_page(page_url, search_term)
                
                if not page_products:
                    st.warning(f"No products found on page {page + 1}")
                    if page == 0:  # If first page has no products, try manual input method
                        break
                    else:
                        break  # End pagination if no more products
                
                all_products.extend(page_products)
                st.success(f"Found {len(page_products)} products on page {page + 1}")
                
                # If we got fewer than 24 products, we've likely reached the end
                if len(page_products) < 24:
                    break
                
            except Exception as e:
                st.warning(f"Error on page {page + 1}: {str(e)}")
                break
        
        return all_products
    
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
            
            # If it's just a term
            elif not url.startswith('http'):
                return url
            
            return None
        except:
            return None

def manual_product_input():
    """Allow manual input of product URLs as backup"""
    st.subheader("🔧 Manual Product Input (Backup Method)")
    st.markdown("If automated scraping doesn't work, you can manually enter product URLs:")
    
    manual_urls = st.text_area(
        "Enter Target product URLs (one per line):",
        placeholder="https://www.target.com/p/-/A-54321\nhttps://www.target.com/p/-/A-12345",
        height=150
    )
    
    if st.button("Scrape Manual URLs", type="secondary"):
        if not manual_urls.strip():
            st.error("Please enter at least one product URL")
            return
        
        urls = [url.strip() for url in manual_urls.strip().split('\n') if url.strip()]
        scraper = TargetScraper()
        products_data = []
        
        progress_bar = st.progress(0)
        
        for i, url in enumerate(urls):
            progress_bar.progress((i + 1) / len(urls))
            st.info(f"Scraping product {i+1}/{len(urls)}")
            
            try:
                product_data = scraper.scrape_individual_product(url)
                if product_data:
                    products_data.append(product_data)
                time.sleep(2)  # Be respectful
            except Exception as e:
                st.warning(f"Failed to scrape {url}: {str(e)}")
        
        if products_data:
            df = pd.DataFrame(products_data)
            st.success(f"Successfully scraped {len(df)} products!")
            st.dataframe(df, use_container_width=True)
            
            # Download functionality
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"target_manual_scrape_{timestamp}.xlsx"
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Product Data', index=False)
            
            output.seek(0)
            
            st.download_button(
                label="📥 Download Excel File",
                data=output,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

class AlternativeTargetScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        })
    
    def scrape_individual_product(self, product_url):
        """Scrape individual product page"""
        try:
            response = self.session.get(product_url, timeout=15)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            product_data = {}
            
            # Extract TCIN from URL
            tcin_match = re.search(r'/A-(\d+)', product_url)
            product_data['TCIN'] = tcin_match.group(1) if tcin_match else 'N/A'
            product_data['URL'] = product_url
            
            # Look for JSON-LD structured data
            json_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_scripts:
                try:
                    json_data = json.loads(script.string)
                    if isinstance(json_data, dict) and json_data.get('@type') == 'Product':
                        product_data['Title'] = json_data.get('name', 'N/A')
                        
                        # Extract price from structured data
                        offers = json_data.get('offers', {})
                        if isinstance(offers, dict) and 'price' in offers:
                            product_data['Price'] = f"${offers['price']}"
                        
                        # Extract rating
                        rating_data = json_data.get('aggregateRating', {})
                        if rating_data:
                            product_data['Rating'] = str(rating_data.get('ratingValue', 'N/A'))
                            product_data['Review_Count'] = str(rating_data.get('reviewCount', 'N/A'))
                        
                        # Extract image
                        image = json_data.get('image')
                        if isinstance(image, list) and image:
                            product_data['Image_URL'] = image[0]
                        elif isinstance(image, str):
                            product_data['Image_URL'] = image
                        
                        break
                        
                except (json.JSONDecodeError, KeyError):
                    continue
            
            # Fallback to HTML parsing if JSON-LD not found
            if 'Title' not in product_data or product_data['Title'] == 'N/A':
                # Try various title selectors
                title_selectors = [
                    'h1[data-test="product-title"]',
                    'h1',
                    '[data-test="product-title"]',
                    '.ProductTitle'
                ]
                
                for selector in title_selectors:
                    title_elem = soup.select_one(selector)
                    if title_elem:
                        product_data['Title'] = title_elem.get_text(strip=True)
                        break
                
                if 'Title' not in product_data:
                    product_data['Title'] = 'N/A'
            
            # Set defaults for missing fields
            for field in ['Price', 'Rating', 'Review_Count', 'Image_URL']:
                if field not in product_data:
                    product_data[field] = 'N/A'
            
            return product_data
            
        except Exception as e:
            st.warning(f"Error scraping {product_url}: {str(e)}")
            return None

def main():
    st.title("🎯 Target Brand Insights Scraper")
    st.markdown("Extract product details from Target.com")
    
    # Important notice
    st.warning("⚠️ **Important**: Due to Target's anti-bot protection, automated scraping may be limited. Manual product URL input is recommended for reliable results.")
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        max_pages = st.slider("Maximum pages to scrape", 1, 10, 3)
        st.info("Reduced default pages due to rate limiting")
    
    # Method selection
    method = st.radio(
        "Choose scraping method:",
        ["🔍 Search Term/URL (Automated)", "📝 Manual Product URLs (Recommended)"],
        help="Manual method is more reliable due to Target's bot protection"
    )
    
    if method == "🔍 Search Term/URL (Automated)":
        # Main interface
        st.markdown("### Enter Search Term or URL")
        
        input_url = st.text_input(
            "Target Search Term or URL:",
            placeholder="yoobi OR https://www.target.com/s?searchTerm=yoobi",
            help="Enter either a search term or Target search URL"
        )
        
        # Convert input to proper search URL if needed
        if input_url:
            if input_url.startswith('http'):
                if '/b/' in input_url:
                    # Convert brand URL to search URL
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
                search_url = f"https://www.target.com/s?searchTerm={quote(input_url)}"
                st.info(f"🔍 Using search URL: {search_url}")
        else:
            search_url = ""
        
        if st.button("Start Automated Scraping", type="primary"):
            if not search_url:
                st.error("Please enter a search term or URL")
                return
            
            scraper = TargetScraper()
            
            # Progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("🔍 Attempting to extract products...")
                products_data = scraper.get_all_products(search_url, max_pages)
                
                if not products_data:
                    st.error("❌ Automated scraping failed. Please try the Manual Product URLs method below.")
                    st.markdown("""
                    **Why this might happen:**
                    - Target's bot protection blocked the request
                    - Page structure has changed
                    - Network restrictions
                    
                    **Solution**: Use the Manual Product URLs method for guaranteed results.
                    """)
                    return
                
                # Convert to DataFrame
                df = pd.DataFrame(products_data)
                st.success(f"✅ Successfully scraped {len(df)} products!")
                
                # Display results and download functionality
                display_results(df)
                
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                st.info("💡 Try the Manual Product URLs method for more reliable results.")
            
            finally:
                progress_bar.empty()
                status_text.empty()
    
    else:
        # Manual input method
        manual_product_input()

def display_results(df):
    """Display results and provide download functionality"""
    # Display data preview
    st.subheader("📊 Data Preview")
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
    filename = f"target_products_{timestamp}.xlsx"
    
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

# Add the missing methods to TargetScraper class
TargetScraper.get_all_products = lambda self, search_url, max_pages=5: self.get_all_products_impl(search_url, max_pages)
TargetScraper.scrape_individual_product = lambda self, url: AlternativeTargetScraper().scrape_individual_product(url)

def get_all_products_impl(self, search_url, max_pages=5):
    """Implementation of get_all_products for TargetScraper"""
    all_products = []
    search_term = self.extract_search_term_from_url(search_url)
    
    if not search_term:
        st.error("Could not extract search term from URL")
        return []
    
    st.info(f"Searching for: '{search_term}'")
    
    # Try different page offsets
    for page in range(max_pages):
        offset = page * 24
        page_url = f"https://www.target.com/s?searchTerm={quote(search_term)}&offset={offset}"
        
        st.info(f"Scraping page {page + 1} (offset: {offset})...")
        
        try:
            page_products = self.extract_product_data_from_page(page_url, search_term)
            
            if not page_products:
                st.warning(f"No products found on page {page + 1}")
                if page == 0:  # If first page has no products, stop
                    break
                else:
                    break  # End pagination if no more products
            
            all_products.extend(page_products)
            st.success(f"Found {len(page_products)} products on page {page + 1}")
            
            # If we got fewer than 24 products, we've likely reached the end
            if len(page_products) < 24:
                break
            
        except Exception as e:
            st.warning(f"Error on page {page + 1}: {str(e)}")
            break
    
    return all_products

# Monkey patch the method
TargetScraper.get_all_products_impl = get_all_products_impl

# Instructions and help
st.sidebar.markdown("---")
with st.sidebar.expander("ℹ️ How to Get Product URLs"):
    st.markdown("""
    **To get Yoobi product URLs manually:**
    
    1. Go to Target.com
    2. Search for "yoobi"
    3. Right-click each product → "Copy link address"
    4. Paste URLs in the Manual Input section
    
    **URL Format:**
    `https://www.target.com/p/product-name/A-12345`
    """)

with st.expander("📖 Instructions & Tips"):
    st.markdown("""
    **Method 1: Automated Search (May be blocked)**
    - Enter just the brand name: `yoobi`
    - Or use search URL: `https://www.target.com/s?searchTerm=yoobi`
    
    **Method 2: Manual URLs (Recommended)**
    - Go to Target.com and search for your brand
    - Copy individual product URLs
    - Paste them in the Manual Input section
    
    **Why Manual Works Better:**
    - Target has strong bot protection
    - Manual method bypasses automated detection
    - More reliable for getting complete data
    
    **Data Extracted:**
    - TCIN, Title, Image URL, Price, Rating, Review Count, Product URL
    """)

st.markdown("---")
st.caption("⚠️ For educational purposes. Respect Target.com's terms of service and use reasonable delays.")

if __name__ == "__main__":
    main()