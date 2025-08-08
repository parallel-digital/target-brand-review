import streamlit as st
import pandas as pd
import re
import time
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from typing import List, Dict, Optional
import os
import tempfile

# Try to import selenium components
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    st.error("Selenium is not installed. Please install the required dependencies.")

# Page configuration
st.set_page_config(
    page_title="Target Product Scraper",
    page_icon="🎯",
    layout="wide"
)

class TargetScraper:
    def __init__(self):
        self.driver = None
        self.setup_driver()
    
    def setup_driver(self):
        """Setup Chrome driver with appropriate options"""
        if not SELENIUM_AVAILABLE:
            st.error("Selenium not available. Please check installation.")
            return
            
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Additional options for cloud deployment
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--single-process")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-sync")
        
        try:
            # Streamlit Cloud specific paths
            chromium_paths = [
                '/usr/bin/chromium',
                '/usr/bin/chromium-browser', 
                '/usr/bin/google-chrome',
                '/usr/bin/google-chrome-stable'
            ]
            
            chromium_path = None
            for path in chromium_paths:
                if os.path.exists(path):
                    chromium_path = path
                    break
            
            if chromium_path:
                st.info(f"Using system Chrome at: {chromium_path}")
                chrome_options.binary_location = chromium_path
                
                # Try to find chromedriver
                driver_paths = [
                    '/usr/bin/chromedriver',
                    '/usr/local/bin/chromedriver'
                ]
                
                driver_path = None
                for path in driver_paths:
                    if os.path.exists(path):
                        driver_path = path
                        break
                
                if driver_path:
                    service = Service(driver_path)
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                else:
                    # Try without explicit service path
                    self.driver = webdriver.Chrome(options=chrome_options)
            else:
                # Fallback to ChromeDriverManager
                st.info("Using ChromeDriverManager...")
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            self.driver.implicitly_wait(10)
            st.success("Chrome driver initialized successfully!")
            
        except Exception as e:
            st.error(f"Failed to initialize Chrome driver: {str(e)}")
            st.info("This might be a Streamlit Cloud configuration issue. Check the logs for more details.")
            self.driver = None
    
    def extract_tcin_from_url(self, url: str) -> Optional[str]:
        """Extract TCIN from product URL patterns"""
        if not url:
            return None
            
        patterns = [
            r'/p/[^/]+-/A-(\d+)',
            r'tcin[=:](\d+)',
            r'/(\d{8})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def wait_for_products_to_load(self, timeout=20):
        """Wait for product elements to load on the page"""
        selectors_to_try = [
            '[data-test="@web/site-top-of-funnel/ProductCardWrapper"]',
            '[data-test="product-card"]',
            '[data-test*="product"]',
            'a[href*="/p/"]',
            '[data-test="@web/ProductCard/ProductCardVariantDefault"]'
        ]
        
        for selector in selectors_to_try:
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                return True
            except TimeoutException:
                continue
        
        return False
    
    def scroll_to_load_all_products(self):
        """Scroll down to trigger lazy loading of all products"""
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        while True:
            # Scroll to bottom
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            # Wait for new content to load
            time.sleep(2)
            
            # Calculate new scroll height
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                break
                
            last_height = new_height
    
    def scrape_page(self, url: str) -> List[Dict]:
        """Scrape a single page for product information"""
        try:
            st.info(f"Loading page: {url}")
            self.driver.get(url)
            
            # Wait for products to load
            if not self.wait_for_products_to_load():
                st.warning("Products did not load within timeout period")
                return []
            
            # Scroll to load all products (lazy loading)
            st.info("Loading all products (handling lazy loading)...")
            self.scroll_to_load_all_products()
            
            # Give extra time for all content to render
            time.sleep(3)
            
            products = []
            
            # Multiple selectors for product containers (updated for current Target structure)
            product_selectors = [
                '[data-test="@web/site-top-of-funnel/ProductCardWrapper"]',
                '[data-test="@web/ProductCard/ProductCardVariantDefault"]',
                '[data-test="product-card"]',
                '[data-test*="ProductCard"]',
                '[data-test*="sponsor"]',  # Specifically look for sponsored products
                '[data-test*="ad"]',       # Ad-related selectors
                'article[data-test*="product"]',
                'div[data-test*="product"]',
                'a[href*="/p/"]'
            ]
            
            product_elements = []
            for selector in product_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        product_elements = elements
                        st.success(f"Found {len(elements)} product elements using selector: {selector}")
                        break
                except Exception as e:
                    continue
            
            if not product_elements:
                st.error("No product elements found with any selector")
                # Debug: Save page source for inspection
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                    f.write(self.driver.page_source)
                    st.info(f"Page source saved for debugging: {f.name}")
                return []
            
            for i, element in enumerate(product_elements):
                try:
                    product_data = self.extract_product_data(element)
                    if product_data and product_data.get('tcin'):
                        products.append(product_data)
                        if i % 10 == 0:  # Progress update every 10 products
                            st.info(f"Processed {i+1}/{len(product_elements)} products...")
                except Exception as e:
                    continue
            
            st.success(f"Successfully extracted data from {len(products)} products")
            return products
            
        except Exception as e:
            st.error(f"Error scraping page {url}: {str(e)}")
            return []
    
    def extract_product_data(self, element) -> Dict:
        """Extract product data from a product element"""
        product = {
            'tcin': None,
            'title': None,
            'image': None,
            'rating': None,
            'review_count': None,
            'price': None,
            'is_sponsored': False
        }
        
        try:
            # Check if product is sponsored
            sponsored_indicators = [
                '[data-test*="sponsor"]',
                '.sponsored',
                '[aria-label*="sponsor"]',
                '[data-test*="ad"]',
                'text*="Sponsored"'
            ]
            
            for indicator in sponsored_indicators:
                try:
                    element.find_element(By.CSS_SELECTOR, indicator)
                    product['is_sponsored'] = True
                    break
                except:
                    continue
            
            # Also check for sponsored text in any child elements
            try:
                element_text = element.text.lower()
                if 'sponsored' in element_text or 'ad' in element_text:
                    product['is_sponsored'] = True
            except:
                pass
            
            # Extract TCIN from href attribute
            try:
                link = element.find_element(By.CSS_SELECTOR, 'a[href*="/p/"]')
                href = link.get_attribute('href')
                product['tcin'] = self.extract_tcin_from_url(href)
            except:
                # Try to find TCIN in data attributes
                try:
                    tcin_attr = element.get_attribute('data-test')
                    if tcin_attr:
                        tcin_match = re.search(r'(\d{8})', tcin_attr)
                        if tcin_match:
                            product['tcin'] = tcin_match.group(1)
                except:
                    pass
            
            # Extract title
            title_selectors = [
                'a[data-test="product-title"]',
                '[data-test="product-title"] a',
                'a[href*="/p/"]',
                'h3 a',
                'h2 a'
            ]
            
            for selector in title_selectors:
                try:
                    title_elem = element.find_element(By.CSS_SELECTOR, selector)
                    product['title'] = title_elem.text.strip()
                    # Also extract TCIN from title link if not found yet
                    if not product['tcin']:
                        href = title_elem.get_attribute('href')
                        product['tcin'] = self.extract_tcin_from_url(href)
                    break
                except:
                    continue
            
            # Extract image
            img_selectors = [
                'img[data-test="product-image"]',
                'img[alt*="product"]',
                'img'
            ]
            
            for selector in img_selectors:
                try:
                    img_elem = element.find_element(By.CSS_SELECTOR, selector)
                    src = img_elem.get_attribute('src')
                    if src and ('target.scene7.com' in src or 'target.com' in src):
                        product['image'] = src
                        break
                except:
                    continue
            
            # Extract rating
            rating_selectors = [
                '[data-test="ratings"]',
                '[aria-label*="star"]',
                '.sr-only'
            ]
            
            for selector in rating_selectors:
                try:
                    rating_elem = element.find_element(By.CSS_SELECTOR, selector)
                    text = rating_elem.get_attribute('aria-label') or rating_elem.text
                    rating_match = re.search(r'(\d+\.?\d*)\s*out of 5', text, re.IGNORECASE)
                    if rating_match:
                        product['rating'] = float(rating_match.group(1))
                        break
                except:
                    continue
            
            # Extract review count
            review_selectors = [
                '[data-test="rating-count"]',
                'button[aria-label*="review"]',
                'span[aria-label*="review"]',
                'a[href*="reviews"]'
            ]
            
            for selector in review_selectors:
                try:
                    review_elem = element.find_element(By.CSS_SELECTOR, selector)
                    text = review_elem.text or review_elem.get_attribute('aria-label') or ""
                    review_match = re.search(r'(\d+)', text.replace(',', ''))
                    if review_match:
                        product['review_count'] = int(review_match.group(1))
                        break
                except:
                    continue
            
            # Extract price
            price_selectors = [
                '[data-test="product-price"]',
                '.sr-only:contains("current price")',
                'span[data-test="product-price-current"]'
            ]
            
            for selector in price_selectors:
                try:
                    price_elem = element.find_element(By.CSS_SELECTOR, selector)
                    text = price_elem.text
                    price_match = re.search(r'\$(\d+\.?\d*)', text)
                    if price_match:
                        product['price'] = f"${price_match.group(1)}"
                        break
                except:
                    continue
            
        except Exception as e:
            pass
        
        return product
    
    def get_next_page_url(self) -> Optional[str]:
        """Extract next page URL"""
        next_selectors = [
            'a[data-test="next"]',
            'button[data-test="next"]',
            'a[aria-label="next page"]',
            'button[aria-label="Next page"]'
        ]
        
        for selector in next_selectors:
            try:
                next_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                if next_elem.is_enabled():
                    href = next_elem.get_attribute('href')
                    if href:
                        return href
                    # If it's a button, click it and get current URL
                    current_url = self.driver.current_url
                    next_elem.click()
                    time.sleep(2)
                    new_url = self.driver.current_url
                    if new_url != current_url:
                        return new_url
            except:
                continue
        
        return None
    
    def scrape_all_pages(self, start_url: str, max_pages: int = 10) -> pd.DataFrame:
        """Scrape all pages starting from the given URL"""
        if not self.driver:
            st.error("Browser driver not initialized")
            return pd.DataFrame()
        
        all_products = []
        current_url = start_url
        page_count = 0
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        while page_count < max_pages:
            page_count += 1
            status_text.text(f"Scraping page {page_count}...")
            
            # Scrape current page
            products = self.scrape_page(current_url)
            
            if not products:
                st.warning(f"No products found on page {page_count}. Stopping.")
                break
            
            all_products.extend(products)
            st.success(f"Page {page_count}: Found {len(products)} products")
            
            # Try to find next page
            next_url = self.get_next_page_url()
            
            if not next_url or next_url == current_url:
                st.info("No more pages found.")
                break
            
            current_url = next_url
            progress_bar.progress(min(page_count / max_pages, 1.0))
            
            # Add delay to be respectful
            time.sleep(2)
        
        progress_bar.progress(1.0)
        status_text.text(f"Completed! Scraped {page_count} pages.")
        
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
    
    def close(self):
        """Clean up the driver"""
        if self.driver:
            self.driver.quit()

def main():
    st.title("🎯 Target Product Scraper (JavaScript-Enabled)")
    st.markdown("Extract product information from Target.com search results using Selenium WebDriver")
    
    if not SELENIUM_AVAILABLE:
        st.error("This app requires Selenium and ChromeDriver to handle JavaScript-rendered content.")
        st.markdown("""
        **To fix this, install the required dependencies:**
        ```bash
        pip install selenium webdriver-manager
        ```
        """)
        return
    
    # Sidebar configuration
    st.sidebar.header("Configuration")
    max_pages = st.sidebar.slider("Maximum pages to scrape", 1, 20, 5)
    
    # URL input
    url_input = st.text_input(
        "Enter Target.com URL:",
        placeholder="https://www.target.com/s?searchTerm=your+search+term",
        help="Enter a Target.com search results URL or category page URL"
    )
    
    # Validate URL
    if url_input and not url_input.startswith('https://www.target.com'):
        st.error("Please enter a valid Target.com URL")
        return
    
    if st.button("Start Scraping", type="primary"):
        if not url_input:
            st.error("Please enter a URL")
            return
        
        scraper = None
        try:
            # Initialize scraper
            with st.spinner("Initializing browser..."):
                scraper = TargetScraper()
                
            if not scraper.driver:
                st.error("Failed to initialize browser. Please check your setup.")
                return
            
            # Start scraping
            with st.spinner("Scraping pages..."):
                df = scraper.scrape_all_pages(url_input, max_pages)
            
            if df.empty:
                st.error("No products found. The page might not contain product listings or there might be an issue with the scraping.")
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
                
                # Download options
                st.subheader("Export Data")
                col1, col2 = st.columns(2)
                
                with col1:
                    csv = df.to_csv(index=False)
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
                        df.to_excel(writer, sheet_name='Target Products', index=False)
                    excel_buffer.seek(0)
                    
                    st.download_button(
                        label="📊 Download as Excel",
                        data=excel_buffer.getvalue(),
                        file_name="target_products.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
        
        finally:
            # Clean up
            if scraper:
                scraper.close()

if __name__ == "__main__":
    main()