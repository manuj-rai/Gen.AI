from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency at runtime
    sync_playwright = None


logger = logging.getLogger("portfolio-assistant.web-loader")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 PortfolioAssistantBot/2.0"
)
SKIP_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".css",
    ".js",
    ".zip",
    ".exe",
    ".ico",
    ".woff",
    ".woff2",
    ".mp4",
    ".webm",
    ".mp3",
}


@dataclass
class WebsitePage:
    url: str
    title: str
    text: str


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    normalized = parsed._replace(query="", fragment="")
    clean_url = urlunparse(normalized).rstrip("/")
    return clean_url or url


def _same_domain(url: str, base_netloc: str) -> bool:
    return urlparse(url).netloc == base_netloc


def _should_skip(url: str) -> bool:
    lowered = url.lower()
    return any(lowered.endswith(extension) for extension in SKIP_EXTENSIONS)


def _parse_html(url: str, html: str, base_netloc: str) -> tuple[WebsitePage | None, list[str]]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    body_text = soup.get_text(separator="\n")
    lines = [_clean_text(line) for line in body_text.splitlines()]
    clean_lines = [line for line in lines if line]

    page = None
    if clean_lines:
        page = WebsitePage(
            url=url,
            title=title or url,
            text="\n".join(clean_lines),
        )

    links: list[str] = []
    for link in soup.find_all("a", href=True):
        absolute_url = _normalize_url(urljoin(url, link["href"]))
        if not absolute_url.startswith(("http://", "https://")):
            continue
        if not _same_domain(absolute_url, base_netloc):
            continue
        if _should_skip(absolute_url):
            continue
        links.append(absolute_url)

    return page, links


def _clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _crawl_with_requests(base_url: str, max_pages: int, timeout_seconds: int = 12) -> list[WebsitePage]:
    parsed_base = urlparse(base_url)
    base_netloc = parsed_base.netloc

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    visited: set[str] = set()
    queued = deque([base_url])
    pages: list[WebsitePage] = []

    while queued and len(visited) < max_pages:
        current_url = queued.popleft()
        if current_url in visited:
            continue

        visited.add(current_url)
        logger.info("Scraping %s", current_url)

        try:
            response = session.get(current_url, timeout=timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Failed to fetch %s: %s", current_url, exc)
            continue

        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            logger.info("Skipping non-HTML content at %s", current_url)
            continue

        page, discovered_links = _parse_html(current_url, response.text, base_netloc)
        if page is not None:
            pages.append(page)

        for discovered_url in discovered_links:
            if discovered_url not in visited and discovered_url not in queued:
                queued.append(discovered_url)

    return pages


def _crawl_with_playwright(base_url: str, max_pages: int, timeout_seconds: int = 20) -> list[WebsitePage]:
    if sync_playwright is None:
        raise RuntimeError("Playwright is not available in this environment.")

    parsed_base = urlparse(base_url)
    base_netloc = parsed_base.netloc
    visited: set[str] = set()
    queued = deque([base_url])
    pages: list[WebsitePage] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page_handle = browser.new_page(user_agent=USER_AGENT)
        page_handle.set_default_navigation_timeout(timeout_seconds * 1000)

        try:
            while queued and len(visited) < max_pages:
                current_url = queued.popleft()
                if current_url in visited:
                    continue

                visited.add(current_url)
                logger.info("Scraping with Playwright %s", current_url)

                try:
                    page_handle.goto(current_url, wait_until="domcontentloaded")
                    html = page_handle.content()
                except Exception as exc:
                    logger.warning("Playwright failed to fetch %s: %s", current_url, exc)
                    continue

                parsed_page, discovered_links = _parse_html(current_url, html, base_netloc)
                if parsed_page is not None:
                    pages.append(parsed_page)

                for discovered_url in discovered_links:
                    if discovered_url not in visited and discovered_url not in queued:
                        queued.append(discovered_url)
        finally:
            browser.close()

    return pages


def crawl_website_pages(base_url: str, max_pages: int = 50, use_playwright: bool = False) -> list[WebsitePage]:
    if not base_url:
        return []

    normalized_base_url = base_url if base_url.startswith(("http://", "https://")) else f"https://{base_url}"
    normalized_base_url = _normalize_url(normalized_base_url)

    if use_playwright:
        try:
            pages = _crawl_with_playwright(normalized_base_url, max_pages=max_pages)
            logger.info("Playwright crawl collected %s page(s).", len(pages))
            return pages
        except Exception as exc:
            logger.warning("Playwright crawl failed, falling back to requests: %s", exc)

    pages = _crawl_with_requests(normalized_base_url, max_pages=max_pages)
    logger.info("Requests crawl collected %s page(s).", len(pages))
    return pages


def get_all_pages_from_website(base_url: str, max_pages: int = 50) -> str:
    pages = crawl_website_pages(base_url, max_pages=max_pages)
    blocks = [f"--- Page: {page.url} ---\n{page.text}" for page in pages if page.text]
    return "\n\n".join(blocks)


def fetch_clean_text_from_url(url: str) -> str:
    pages = crawl_website_pages(url, max_pages=1)
    if not pages:
        return ""
    return pages[0].text
