import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

def get_all_pages_from_website(base_url: str, max_pages: int = 50) -> str:
    """
    Crawl all pages from a website (same domain) using requests+BeautifulSoup.
    Returns combined text from up to max_pages.
    """
    if not base_url:
        return ""
    # Ensure URL has scheme
    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url

    # Parse base domain
    parsed_base = urlparse(base_url)
    base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"
    
    # Initialize session with a User-Agent
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
    })

    visited_urls = set()
    urls_to_visit = [base_url]
    all_text_content = []

    print(f"🌐 Starting crawl: {base_url}")
    while urls_to_visit and len(visited_urls) < max_pages:
        current_url = urls_to_visit.pop(0)
        if current_url in visited_urls:
            continue
        visited_urls.add(current_url)
        print(f"📄 Fetching: {current_url}")

        try:
            response = session.get(current_url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ Request failed: {e}")
            continue

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            # Skip non-HTML pages
            print(f"⚠️ Skipping non-HTML content: {current_url}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        # Remove scripts, styles, and other non-content tags
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            page_text = f"\n\n--- Page: {current_url} ---\n\n" + "\n".join(lines)
            all_text_content.append(page_text)
            print(f"✅ Extracted {len(lines)} text lines from {current_url}")
        else:
            print(f"⚠️ No text content on {current_url}")

        # Find and enqueue new links from the same domain
        for link in soup.find_all("a", href=True):
            href = link["href"]
            abs_url = urljoin(current_url, href)
            parsed_link = urlparse(abs_url)
            link_base = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}"
            link_base = link_base.rstrip("/")  # normalize
            # Only follow links on the same domain
            if parsed_link.netloc == parsed_base.netloc:
                if link_base not in visited_urls and link_base not in urls_to_visit:
                    # Skip static file types
                    if not any(link_base.lower().endswith(ext) for ext in 
                               [".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js", 
                                ".pdf", ".zip", ".exe", ".ico", ".woff", ".woff2"]):
                        urls_to_visit.append(link_base)
    combined_text = "\n".join(all_text_content)
    print(f"✅ Crawled {len(visited_urls)} pages. Total lines: {sum(len(page.splitlines()) for page in all_text_content)}")
    return combined_text
