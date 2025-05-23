import requests
from bs4 import BeautifulSoup

def fetch_clean_text_from_url(url: str) -> str:
    try:
        response = requests.get(url, timeout=10)
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
