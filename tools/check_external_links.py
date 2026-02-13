"""Check that all external URLs in skill markdown files return 2xx."""

import asyncio
import re
import sys
from pathlib import Path

import httpx

from config import REFERENCES_DIR, SKILL_MD

CONCURRENCY = 5
TIMEOUT = 10
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds


def find_markdown_files() -> list[Path]:
    """Find all markdown files in the skill directory."""
    files = [SKILL_MD]
    files.extend(sorted(REFERENCES_DIR.glob("*.md")))
    return files


def strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks from markdown text."""
    return re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)


def extract_urls(text: str) -> set[str]:
    """Extract all https:// URLs from markdown text, excluding code blocks."""
    text = strip_code_blocks(text)
    urls = set(re.findall(r"https?://[^\s\)>\]\"'`]+", text))
    # Exclude template/placeholder URLs containing angle brackets
    urls = {u for u in urls if "<" not in u}
    return urls


async def check_url(
    client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore
) -> tuple[str, int | str]:
    """Check a single URL with retries and backoff."""
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.head(url, timeout=TIMEOUT, follow_redirects=True)
                if resp.status_code < 400:
                    return url, resp.status_code
                # Some servers reject HEAD, try GET
                resp = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
                return url, resp.status_code
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                else:
                    return url, str(e)
    return url, "max retries exceeded"


async def run() -> list[str]:
    # Collect all unique URLs
    all_urls: set[str] = set()
    for md_file in find_markdown_files():
        all_urls.update(extract_urls(md_file.read_text()))

    if not all_urls:
        return []

    errors = []
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(headers={"User-Agent": "link-checker/0.1"}) as client:
        tasks = [check_url(client, url, semaphore) for url in sorted(all_urls)]
        results = await asyncio.gather(*tasks)

    for url, status in results:
        if isinstance(status, str):
            errors.append(f"{url} -> error: {status}")
        elif status >= 400:
            errors.append(f"{url} -> HTTP {status}")

    return errors


def main() -> None:
    errors = asyncio.run(run())

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        sys.exit(1)

    print("OK: All external links are live")
    sys.exit(0)
