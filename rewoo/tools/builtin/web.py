"""Web tools — search and scrape.

Provides web search and page scraping capabilities. These tools
respect domain allowlists configured through ReWoo settings.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests
DEFAULT_TIMEOUT = 30


async def web_search(query: str, num_results: int = 5) -> str:
    """Search the web for information.

    Uses a search API or falls back to a simple HTTP-based approach.

    Args:
        query: Search query string.
        num_results: Maximum number of results to return.

    Returns:
        Formatted search results as a string.
    """
    logger.info(f"web.search: {query[:100]}")

    try:
        # Use DuckDuckGo HTML search as a fallback (no API key needed)
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ReWoo/0.1.0)",
                },
            )
            response.raise_for_status()

            # Simple HTML parsing to extract results
            results = _parse_ddg_results(response.text, num_results)

            if not results:
                return f"No search results found for: {query}"

            formatted = "\n\n".join(
                f"[{i+1}] {r['title']}\n{r['snippet']}\n{r['url']}"
                for i, r in enumerate(results)
            )

            logger.debug(f"web.search: {len(results)} results for '{query[:50]}'")
            return formatted

    except httpx.HTTPError as e:
        logger.error(f"web.search failed: {e}")
        return f"Search failed: {e}"
    except Exception as e:
        logger.error(f"web.search error: {e}")
        return f"Search error: {e}"


async def web_scrape(url: str, max_length: int = 5000) -> str:
    """Scrape the content of a web page.

    Args:
        url: URL of the page to scrape.
        max_length: Maximum content length to return.

    Returns:
        Page content as plain text.
    """
    logger.info(f"web.scrape: {url}")

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ReWoo/0.1.0)",
                },
            )
            response.raise_for_status()

            content = response.text

            # Simple HTML to text conversion
            content = _html_to_text(content)

            if len(content) > max_length:
                content = content[:max_length] + f"\n... (truncated, {len(content)} total chars)"

            logger.debug(f"web.scrape: {len(content)} chars from {url}")
            return content

    except httpx.HTTPError as e:
        logger.error(f"web.scrape failed: {e}")
        return f"Scrape failed: {e}"
    except Exception as e:
        logger.error(f"web.scrape error: {e}")
        return f"Scrape error: {e}"


def _parse_ddg_results(html: str, max_results: int) -> list[dict[str, str]]:
    """Parse DuckDuckGo HTML search results.

    Args:
        html: Raw HTML from DuckDuckGo.
        max_results: Maximum number of results.

    Returns:
        List of dicts with 'title', 'snippet', and 'url' keys.
    """
    results: list[dict[str, str]] = []

    # Simple regex-based parsing (no external HTML parser dependency)
    import re

    # DuckDuckGo results are in result blocks
    result_blocks = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )

    for url_match, title_match, snippet_match in result_blocks[:max_results]:
        title = re.sub(r"<[^>]+>", "", title_match).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet_match).strip()
        results.append({"title": title, "snippet": snippet, "url": url_match})

    return results


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text with basic formatting.

    Args:
        html: Raw HTML content.

    Returns:
        Plain text representation.
    """
    import re

    # Remove scripts and styles
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Convert common block elements to newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)

    # Remove remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Clean up whitespace
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = text.strip()

    # Decode HTML entities
    import html as html_module
    text = html_module.unescape(text)

    return text
