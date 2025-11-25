import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Set


def get_all_pages_from_website(base_url: str, max_pages: int = 50) -> str:
    """
    Crawl all static pages from a website using only requests + BeautifulSoup.
    Follows internal links and extracts clean text from each page.
    
    Args:
        base_url: The starting URL (e.g., "https://manuj-rai.vercel.app/")
        max_pages: Maximum number of pages to scrape

    Returns:
        Combined clean text content from all pages
    """
    if not base_url:
        return ""

    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url

    parsed_base = urlparse(base_url)
    base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
    })

    visited_urls: Set[str] = set()
    urls_to_visit: list = [base_url]
    all_text_content = []

    print(f"🌐 Starting to crawl website: {base_url}")
    
    while urls_to_visit and len(visited_urls) < max_pages:
        current_url = urls_to_visit.pop(0)

        if current_url in visited_urls:
            continue

        visited_urls.add(current_url)
        print(f"📄 Scraping: {current_url}")

        try:
            response = session.get(current_url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ Error fetching {current_url}: {e}")
            continue

        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            print(f"⚠️ Skipping non-HTML content: {current_url}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove unwanted tags
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        clean_lines = [line.strip() for line in text.splitlines() if line.strip()]

        if clean_lines:
            page_content = f"\n\n--- Page: {current_url} ---\n\n" + "\n".join(clean_lines)
            all_text_content.append(page_content)
            print(f"✅ Scraped {len(clean_lines)} lines from {current_url}")
        else:
            print(f"⚠️ No content found on {current_url}")

        # Discover internal links
        if len(visited_urls) < max_pages:
            links_found = 0
            for link in soup.find_all("a", href=True):
                href = link["href"]
                absolute_url = urljoin(current_url, href)
                parsed_link = urlparse(absolute_url)

                # Only follow links on same domain
                if parsed_link.netloc == parsed_base.netloc:
                    clean_url = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}".rstrip("/")
                    if clean_url not in visited_urls and clean_url not in urls_to_visit:
                        # Filter out static file types
                        skip_exts = [".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js",
                                     ".zip", ".exe", ".ico", ".woff", ".woff2"]
                        if not any(clean_url.lower().endswith(ext) for ext in skip_exts):
                            urls_to_visit.append(clean_url)
                            links_found += 1

            if links_found:
                print(f"🔗 Found {links_found} new links to crawl")

    print(f"✅ Crawled {len(visited_urls)} pages from {base_domain}")
    print(f"📊 Total content lines: {sum(len(p.splitlines()) for p in all_text_content)}")
    return "\n".join(all_text_content)


# Optional: for legacy single URL scraping
def fetch_clean_text_from_url(url: str) -> str:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        clean_lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(clean_lines)
    except Exception as e:
        print(f"❌ Error scraping {url}: {e}")
        return ""
