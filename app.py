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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.products = []
    
    def extract_tcin_from_url(self, url):
        """Extract TCIN from product URL"""
        tcin_match = re.search(r'/A-(\d+)', url)
        if tcin_match:
            return tcin_match.group(1)
        return None
    
    def get_product_details(self, product_url):
        """Extract product details from individual product page"""
        try:
            response = self.session.get(product_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            product_data = {}
            
            # Extract TCIN from URL
            product_data['TCIN'] = self.extract_tcin_from_url(product_url)
            product_data['URL'] = product_url
            
            # Extract title
            title_elem = soup.find('h1', {'data-test': 'product-title'}) or soup.find('h1')
            product_data['Title'] = title_elem.get_text(strip=True) if title_elem else "N/A"
            
            # Extract image URL
            img_elem = soup.find('img', {'data-test': 'product-image'}) or soup.find('img', {'alt': True})
            product_data['Image_URL'] = img_elem.get('src') if img_elem else "N/A"
            
            # Extract price information
            price_elem = soup.find('[data-test="product-price"]') or soup.find('span', string=re.compile(r'\$\d+'))
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r'\$(\d+\.?\d*)', price_text)
                product_data['Price'] = f"${price_match.group(1)}" if price_match else price_text
            else:
                product_data['Price'] = "N/A"
            
            # Extract ratings
            rating_elem = soup.find('[data-test="ratings-and-reviews"]') or soup.find('span', string=re.compile(r'\d+\.\d+'))
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                product_data['Rating'] = rating_match.group(1) if rating_match else "N/A"
            else:
                product_data['Rating'] = "N/A"
            
            # Extract review count
            review_elem = soup.find('a', {'data-test': 'reviews-link'}) or soup.find(string=re.compile(r'\d+\s+review'))
            if review_elem:
                if hasattr(review_elem, 'get_text'):
                    review_text = review_elem.get_text(strip=True)
                else:
                    review_text = str(review_elem)
                review_match = re.search(r'(\d+)', review_text)
                product_data['Review_Count'] = review_match.group(1) if review_match else "N/A"
            else:
                product_data['Review_Count'] = "N/A"
            
            return product_data
            
        except Exception as e:
            st.error(f"Error scraping product {product_url}: {str(e)}")
            return None
    
    def get_brand_page_products(self, brand_url):
        """Extract all product URLs from brand page"""
        try:
            response = self.session.get(brand_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find product links
            product_links = []
            
            # Common selectors for Target product links
            link_selectors = [
                'a[href*="/p/"]',
                'a[data-test="product-title"]',
                'a[href*="/A-"]',
                '.ProductCardImage a',
                '[data-test="product-image"] a'
            ]
            
            for selector in link_selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href')
                    if href and '/p/' in href:
                        full_url = urljoin(brand_url, href)
                        if full_url not in product_links:
                            product_links.append(full_url)
            
            return product_links
            
        except Exception as e:
            st.error(f"Error accessing brand page: {str(e)}")
            return []
    
    def scrape_all_pages(self, base_url, max_pages=10):
        """Scrape multiple pages of products"""
        all_product_links = []
        
        # Get products from first page
        initial_links = self.get_brand_page_products(base_url)
        all_product_links.extend(initial_links)
        
        # Try to find additional pages
        for page in range(2, max_pages + 1):
            try:
                # Common pagination patterns for Target
                page_url = f"{base_url}?offset={24 * (page - 1)}"  # Target typically shows 24 items per page
                
                page_links = self.get_brand_page_products(page_url)
                if not page_links or page_links == initial_links:
                    break
                    
                all_product_links.extend(page_links)
                time.sleep(1)  # Be respectful to the server
                
            except Exception as e:
                st.warning(f"Could not access page {page}: {str(e)}")
                break
        
        return list(set(all_product_links))  # Remove duplicates

def main():
    st.title("🎯 Target Brand Insights Scraper")
    st.markdown("Extract product details from Target.com brand pages")
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        max_pages = st.slider("Maximum pages to scrape", 1, 20, 5)
        delay_between_requests = st.slider("Delay between requests (seconds)", 0.5, 3.0, 1.0)
    
    # Main interface
    brand_url = st.text_input(
        "Enter Target Brand Page URL:",
        placeholder="https://www.target.com/b/brand-name/-/N-xxxxx",
        help="Enter the full URL of the Target brand page you want to scrape"
    )
    
    if st.button("Start Scraping", type="primary"):
        if not brand_url:
            st.error("Please enter a brand URL")
            return
        
        if "target.com" not in brand_url.lower():
            st.error("Please enter a valid Target.com URL")
            return
        
        scraper = TargetScraper()
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            # Step 1: Get all product links
            status_text.text("🔍 Finding all products...")
            product_links = scraper.scrape_all_pages(brand_url, max_pages)
            
            if not product_links:
                st.error("No products found. Please check the URL or try a different brand page.")
                return
            
            st.success(f"Found {len(product_links)} products to scrape")
            
            # Step 2: Scrape each product
            products_data = []
            
            for i, product_url in enumerate(product_links):
                progress = (i + 1) / len(product_links)
                progress_bar.progress(progress)
                status_text.text(f"📦 Scraping product {i+1}/{len(product_links)}")
                
                product_data = scraper.get_product_details(product_url)
                if product_data:
                    products_data.append(product_data)
                
                time.sleep(delay_between_requests)
            
            # Step 3: Create DataFrame and display results
            if products_data:
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
                    avg_rating = df[df['Rating'] != 'N/A']['Rating'].astype(float).mean()
                    st.metric("Avg Rating", f"{avg_rating:.1f}" if not pd.isna(avg_rating) else "N/A")
                with col3:
                    total_reviews = df[df['Review_Count'] != 'N/A']['Review_Count'].astype(int).sum()
                    st.metric("Total Reviews", f"{total_reviews:,}" if total_reviews > 0 else "N/A")
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
            
            else:
                st.error("No product data could be extracted. The page structure might have changed.")
        
        except Exception as e:
            st.error(f"An error occurred during scraping: {str(e)}")
        
        finally:
            progress_bar.empty()
            status_text.empty()

    # Instructions
    with st.expander("ℹ️ Instructions"):
        st.markdown("""
        **How to use this app:**
        
        1. **Find a Target brand page**: Go to Target.com and navigate to a brand page (e.g., search for a brand and go to their dedicated page)
        
        2. **Copy the URL**: The URL should look something like:
           - `https://www.target.com/b/nike/-/N-xxxxx`
           - `https://www.target.com/b/apple/-/N-xxxxx`
        
        3. **Paste and scrape**: Enter the URL above and click "Start Scraping"
        
        4. **Download results**: Once complete, download the Excel file with all product data
        
        **Data extracted:**
        - TCIN (Target product ID)
        - Product Title
        - Image URL
        - Price/ASP
        - Rating
        - Review Count
        - Product URL
        
        **Note**: Please be respectful of Target's servers. Use reasonable delays between requests.
        """)
    
    # Disclaimer
    st.markdown("---")
    st.caption("⚠️ This tool is for educational purposes. Please respect Target.com's robots.txt and terms of service.")

if __name__ == "__main__":
    main()