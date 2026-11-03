"""Fetch PubMed Central open-access articles and parse them into source packets.

Each versioned article ID (PMC12345678.1) is checked against the license policy, its JATS XML is
downloaded from the PMC open-access cloud, and parsed into numbered source segments. Packets are
cached as SOURCES/<article>.json so reruns do not refetch.
"""
from __future__ import annotations

from pathlib import Path
import re

from .corpus import fetch_article
from .literature_client import LiteratureClient, LiteratureConfig
from .run_files import read, write


def client(cache_dir):
    return LiteratureClient(LiteratureConfig(
        cache=str(Path(cache_dir) / 'metadata.sqlite'), concurrency=1, cloud_requests_per_second=3, retries=1,
        max_xml_bytes=2_000_000, max_metadata_bytes=1_000_000, max_versions=8, max_listing_pages=2))


async def acquire(article_ids, cache_dir, *, permissive_only=True):
    """Return ({article_id: source packet}, {article_id: reason}) for the requested articles."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    sources, skipped = {}, {}
    literature = client(cache_dir)
    try:
        for aid in article_ids:
            match = re.fullmatch(r'(PMC\d+)\.(\d+)', aid)
            if not match:
                raise ValueError(f'Use versioned PMC article IDs such as PMC12345678.1, not {aid!r}')
            path = cache_dir / f'{aid}.json'
            if path.exists():
                sources[aid] = read(path)
                continue
            article = await fetch_article(literature, match[1], int(match[2]), permissive_only=permissive_only)
            if article.get('status') != 'eligible':
                skipped[aid] = {k: article[k] for k in ('status', 'versions', 'rejected', 'license') if k in article}
                continue
            if article['article_id'] != aid:
                raise ValueError(f'Fetched {article["article_id"]} for {aid}')
            write(path, article)
            sources[aid] = article
    finally:
        await literature.close()
    return sources, skipped
