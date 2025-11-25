import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Set

def fetch_clean_text_from_url(url: str) -> str:
    """
    Fetch and extract clean text from a single URL.
    """
    try:
        response = requests.get(url, timeout=10, allow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove scripts, styles, navigation, and hidden elements
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        clean_lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(clean_lines)

    except Exception as e:
        print(f"❌ Error scraping {url}: {e}")
        return ""

def get_all_pages_from_website(base_url: str, max_pages: int = 50) -> str:
    """
    Crawl all pages from a website starting from the base URL.
    Only follows links within the same domain.
    
    Args:
        base_url: The starting URL (e.g., "https://manuj-rai.vercel.app/")
        max_pages: Maximum number of pages to scrape (default: 50)
    
    Returns:
        Combined text content from all scraped pages
    """
    if not base_url:
        return ""
    
    # Ensure base_url has a scheme
    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url
    
    # Normalize base URL
    parsed_base = urlparse(base_url)
    base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"
    
    visited_urls: Set[str] = set()
    urls_to_visit: list = [base_url]
    all_text_content = []
    
    print(f"🌐 Starting to crawl website: {base_url}")
    
    while urls_to_visit and len(visited_urls) < max_pages:
        current_url = urls_to_visit.pop(0)
        
        # Skip if already visited
        if current_url in visited_urls:
            continue
        
        # Mark as visited
        visited_urls.add(current_url)
        print(f"📄 Scraping: {current_url}")
        
        try:
            # Fetch the page
            response = requests.get(current_url, timeout=10, allow_redirects=True)
            response.raise_for_status()
            
            # Skip non-HTML content
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type:
                print(f"⚠️ Skipping non-HTML content: {current_url}")
                continue
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Extract clean text from this page
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            
            # Get page text with URL as header for context
            page_text = soup.get_text(separator="\n")
            clean_lines = [line.strip() for line in page_text.splitlines() if line.strip()]
            
            if clean_lines:
                # Add URL context to the content
                page_content = f"\n\n--- Page: {current_url} ---\n\n" + "\n".join(clean_lines)
                all_text_content.append(page_content)
                print(f"✅ Scraped {len(clean_lines)} lines from {current_url}")
            
            # Find all links on this page
            if len(visited_urls) < max_pages:
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    absolute_url = urljoin(current_url, href)
                    parsed_link = urlparse(absolute_url)
                    
                    # Only follow links from the same domain
                    if parsed_link.netloc == parsed_base.netloc:
                        # Remove fragment identifiers and query params for deduplication
                        clean_url = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}"
                        # Remove trailing slash for consistency
                        clean_url = clean_url.rstrip("/") or clean_url
                        
                        if clean_url not in visited_urls and clean_url not in urls_to_visit:
                            # Filter out common non-content URLs
                            skip_extensions = [".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", 
                                             ".css", ".js", ".zip", ".exe", ".ico"]
                            if not any(clean_url.lower().endswith(ext) for ext in skip_extensions):
                                urls_to_visit.append(clean_url)
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching {current_url}: {e}")
        except Exception as e:
            print(f"❌ Error processing {current_url}: {e}")
    
    combined_text = "\n".join(all_text_content)
    print(f"✅ Crawled {len(visited_urls)} pages from {base_domain}")
    return combined_text

# Backward compatibility - single URL function
def fetch_clean_text_from_url_single(url: str) -> str:
    """
    Legacy function for single URL scraping.
    For new code, use get_all_pages_from_website() instead.
    """
    return fetch_clean_text_from_url(url)