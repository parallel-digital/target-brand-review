import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
import json
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
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def extract_tcin_from_url(self, url: str) -> Optional[str]:
        """Extract TCIN from product URL patterns"""
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
    
    def extract_tcin_from_element(self, element) -> Optional[str]:
        """Extract TCIN from various element attributes"""
        # Check data attributes
        for attr in ['data-test', 'data-tcin', 'data-product-id']:
            if element.get(attr):
                tcin_match = re.search(r'(\d{8})', str(element.get(attr)))
                if tcin_match:
                    return tcin_match.group(1)
        
        # Check href attributes
        if element.get('href'):
            return self.extract_tcin_from_url(element.get('href'))
        
        # Check parent and child elements
        for parent in element.parents:
            if parent.name and parent.get('href'):
                tcin = self.extract_tcin_from_url(parent.get('href'))
                if tcin:
                    return tcin
        
        return None
    
    def scrape_page(self, url: str) -> List[Dict]:
        """Scrape a single page for product information"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            products = []
            
            # Multiple selectors for product containers
            product_selectors = [
                '[data-test="product-card"]',
                '[data-test*="product"]',
                '.ProductCardImageContainer',
                '.ProductCard',
                'article[data-test*="product"]',
                'div[data-test*="product"]'
            ]
            
            product_elements = []
            for selector in product_selectors:
                elements = soup.select(selector)
                if elements:
                    product_elements.extend(elements)
                    break  # Use the first selector that finds elements
            
            if not product_elements:
                # Fallback: look for links containing product URLs
                product_links = soup.find_all('a', href=re.compile(r'/p/[^/]+-/A-\d+'))
                for link in product_links:
                    parent = link.find_parent(['div', 'article']) 
                    if parent:
                        product_elements.append(parent)
            
            for element in product_elements:
                product_data = self.extract_product_data(element)
                if product_data and product_data.get('tcin'):
                    products.append(product_data)
            
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
            'review_count': None
        }
        
        # Extract TCIN
        product['tcin'] = self.extract_tcin_from_element(element)
        
        # Extract title
        title_selectors = [
            'a[data-test="product-title"]',
            '[data-test="product-title"]',
            '.ProductCardProductTitle a',
            'h3 a',
            'h2 a',
            'a[href*="/p/"]'
        ]
        
        for selector in title_selectors:
            title_elem = element.select_one(selector)
            if title_elem:
                product['title'] = title_elem.get_text(strip=True)
                # Also try to extract TCIN from title link
                if not product['tcin'] and title_elem.get('href'):
                    product['tcin'] = self.extract_tcin_from_url(title_elem.get('href'))
                break
        
        # Extract image
        img_selectors = [
            'img[data-test="product-image"]',
            '.ProductCardImage img',
            'img[alt*="product"]',
            'img'
        ]
        
        for selector in img_selectors:
            img_elem = element.select_one(selector)
            if img_elem and img_elem.get('src'):
                src = img_elem.get('src')
                if 'target.scene7.com' in src or 'target.com' in src:
                    product['image'] = src
                    break
        
        # Extract rating
        rating_selectors = [
            '[data-test="ratings"] span',
            '.sr-only',
            '[aria-label*="star"]',
            '.rating span'
        ]
        
        for selector in rating_selectors:
            rating_elem = element.select_one(selector)
            if rating_elem:
                text = rating_elem.get_text(strip=True)
                rating_match = re.search(r'(\d+\.?\d*)\s*out of 5', text, re.IGNORECASE)
                if rating_match:
                    product['rating'] = float(rating_match.group(1))
                    break
        
        # Extract review count
        review_selectors = [
            '[data-test="rating-count"]',
            'button[aria-label*="review"]',
            'span[aria-label*="review"]',
            'a[href*="reviews"]'
        ]
        
        for selector in review_selectors:
            review_elem = element.select_one(selector)
            if review_elem:
                text = review_elem.get_text(strip=True)
                review_match = re.search(r'(\d+)', text.replace(',', ''))
                if review_match:
                    product['review_count'] = int(review_match.group(1))
                    break
        
        return product
    
    def get_next_page_url(self, current_url: str, soup: BeautifulSoup) -> Optional[str]:
        """Extract next page URL"""
        # Look for next page button
        next_selectors = [
            'a[data-test="next"]',
            'button[data-test="next"]',
            'a[aria-label="next page"]',
            '.next',
            'a:contains("Next")'
        ]
        
        for selector in next_selectors:
            next_elem = soup.select_one(selector)
            if next_elem and next_elem.get('href'):
                return urljoin(current_url, next_elem.get('href'))
        
        # Try pagination logic based on URL parameters
        parsed = urlparse(current_url)
        query_params = parse_qs(parsed.query)
        
        # Check for offset parameter
        if 'offset' in query_params:
            try:
                current_offset = int(query_params['offset'][0])
                new_offset = current_offset + 24  # Target typically shows 24 products per page
                query_params['offset'] = [str(new_offset)]
                new_query = urlencode(query_params, doseq=True)
                return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
            except (ValueError, IndexError):
                pass
        
        return None
    
    def scrape_all_pages(self, start_url: str, max_pages: int = 10) -> pd.DataFrame:
        """Scrape all pages starting from the given URL"""
        all_products = []
        current_url = start_url
        page_count = 0
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        while current_url and page_count < max_pages:
            page_count += 1
            status_text.text(f"Scraping page {page_count}...")
            
            # Get page content
            try:
                response = self.session.get(current_url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Scrape current page
                products = self.scrape_page(current_url)
                
                if not products:
                    st.warning(f"No products found on page {page_count}. Stopping.")
                    break
                
                all_products.extend(products)
                st.success(f"Page {page_count}: Found {len(products)} products")
                
                # Find next page URL
                next_url = self.get_next_page_url(current_url, soup)
                
                if not next_url:
                    st.info("No more pages found.")
                    break
                
                current_url = next_url
                progress_bar.progress(min(page_count / max_pages, 1.0))
                
                # Add delay to be respectful
                time.sleep(1)
                
            except Exception as e:
                st.error(f"Error on page {page_count}: {str(e)}")
                break
        
        progress_bar.progress(1.0)
        status_text.text(f"Completed! Scraped {page_count} pages.")
        
        # Convert to DataFrame
        df = pd.DataFrame(all_products)
        
        # Remove duplicates based on TCIN
        if not df.empty and 'tcin' in df.columns:
            df = df.drop_duplicates(subset=['tcin'], keep='first')
        
        return df

def main():
    st.title("🎯 Target Product Scraper")
    st.markdown("Extract product information from Target.com search results")
    
    # Sidebar configuration
    st.sidebar.header("Configuration")
    max_pages = st.sidebar.slider("Maximum pages to scrape", 1, 50, 10)
    
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
        
        # Initialize scraper
        scraper = TargetScraper()
        
        # Start scraping
        with st.spinner("Initializing scraper..."):
            df = scraper.scrape_all_pages(url_input, max_pages)
        
        if df.empty:
            st.error("No products found. The page structure might have changed or the URL might not contain product listings.")
        else:
            st.success(f"Successfully scraped {len(df)} unique products!")
            
            # Display results
            st.subheader("Scraped Data Preview")
            st.dataframe(df, use_container_width=True)
            
            # Display statistics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Products", len(df))
            with col2:
                st.metric("Products with Ratings", df['rating'].notna().sum())
            with col3:
                st.metric("Products with Reviews", df['review_count'].notna().sum())
            with col4:
                avg_rating = df['rating'].mean()
                st.metric("Average Rating", f"{avg_rating:.2f}" if pd.notna(avg_rating) else "N/A")
            
            # Download options
            st.subheader("Export Data")
            col1, col2 = st.columns(2)
            
            with col1:
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download as CSV",
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
                    label="Download as Excel",
                    data=excel_buffer.getvalue(),
                    file_name="target_products.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

if __name__ == "__main__":
    main()