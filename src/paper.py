import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import arxiv
import feedparser
import torch
from loguru import logger
from sentence_transformers import SentenceTransformer

ARXIV_ID_RE = re.compile(r"^(\d{4}\.\d{4,5}|[a-z\-]+(\.[A-Z]{2})?/\d{7})(v\d+)?$")
INTEREST_PROMPT = (
    "Instruct: Given a research interest, retrieve arXiv paper abstracts relevant to it\nQuery: "
)


@dataclass
class ArxivPaper:
    title: str
    summary: str
    authors: list[str]
    arxiv_id: str
    categories: list[str] = field(default_factory=list)
    # Filled by the embedding ranker
    score: float = 0.0
    interest: str = ""
    # Filled by the LLM reviewer
    relevance: float | None = None
    quality: float | None = None
    tldr: str = ""
    reason: str = ""
    # Filled by resources.attach_resources
    resources: Any = None

    @property
    def abs_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"

    @property
    def pdf_url(self) -> str:
        return f"https://arxiv.org/pdf/{self.arxiv_id}"

    @property
    def final_score(self) -> float:
        if self.relevance is None or self.quality is None:
            return self.score
        return 0.5 * self.relevance + 0.5 * self.quality

    @classmethod
    def from_result(cls, r: arxiv.Result) -> "ArxivPaper":
        return cls(
            title=r.title,
            summary=r.summary.replace("\n", " ").strip(),
            authors=[a.name for a in r.authors],
            arxiv_id=re.sub(r"v\d+$", "", r.get_short_id()),
            categories=list(r.categories),
        )

    @classmethod
    def from_feed_entry(cls, entry) -> "ArxivPaper":
        """Construct ArxivPaper directly from a feedparser RSS entry, avoiding arXiv API calls."""
        raw_summary = entry.summary
        abstract_marker = re.search(r"Abstract:\s*", raw_summary)
        if abstract_marker:
            raw_summary = raw_summary[abstract_marker.end():]
        # The RSS feed puts all authors into a single comma-separated name
        authors = [
            name.strip()
            for a in entry.get("authors", [])
            for name in a.get("name", "").split(",")
            if name.strip()
        ]
        return cls(
            title=" ".join(entry.title.split()),
            summary=" ".join(raw_summary.split()),
            authors=authors,
            arxiv_id=re.sub(r"v\d+$", "", entry.id.removeprefix("oai:arXiv.org:")),
            categories=[t.term for t in entry.get("tags", [])],
        )


def fetch_feed(url: str, retries: int = 3, delay: int = 60):
    """Fetch the RSS feed, retrying so a network hiccup is not mistaken for "no papers today"."""
    for attempt in range(1, retries + 1):
        feed = feedparser.parse(url)
        if feed.get("status") == 200 and "title" in feed.feed:
            return feed
        logger.warning(f"RSS fetch attempt {attempt}/{retries} failed: {feed.get('bozo_exception') or feed.get('status')}")
        if attempt < retries:
            time.sleep(delay)
    raise ConnectionError(f"Failed to fetch {url}")


def get_arxiv_paper(query: str, debug: bool = False) -> list[ArxivPaper]:
    if debug:
        logger.debug("Retrieve 30 arxiv papers regardless of the date.")
        client = arxiv.Client(num_retries=3, delay_seconds=5)
        search = arxiv.Search(
            query="cat:cs.CL", sort_by=arxiv.SortCriterion.SubmittedDate, max_results=30
        )
        return [ArxivPaper.from_result(r) for r in client.results(search)]

    feed = fetch_feed(f"https://rss.arxiv.org/atom/{query}")
    if "Feed error for query" in feed.feed.get("title", ""):
        raise Exception(f"Invalid ARXIV_QUERY: {query}.")
    # "new" are first submissions, "cross" are new papers cross-listed from other
    # categories (e.g. stat.ML); revisions ("replace*") were already announced before.
    papers: dict[str, ArxivPaper] = {}
    for entry in feed.entries:
        if entry.get("arxiv_announce_type") in ("new", "cross"):
            paper = ArxivPaper.from_feed_entry(entry)
            papers.setdefault(paper.arxiv_id, paper)
    logger.info(f"Found {len(papers)} new papers in RSS feed.")
    return list(papers.values())


def load_interests(path: str | Path) -> dict[str, list[str]]:
    """
    Load research interests from a plain text file, grouped by "## <name>" headers.

    Under each header, every non-empty line not starting with "#" is either:
      - an arXiv ID (e.g. 2406.04093), whose title and abstract are fetched as a reference, or
      - a free-text description of the research interest.
    Lines before the first header go to a group named "General".
    """
    path = Path(path)
    if not path.exists():
        logger.warning(f"Interests file {path} not found.")
        return {}

    groups: dict[str, list[str]] = {}
    current = "General"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("##"):
            current = line.lstrip("#").strip()
        elif line and not line.startswith("#"):
            groups.setdefault(current, []).append(line)

    ids = [line for lines in groups.values() for line in lines if ARXIV_ID_RE.match(line)]
    if ids:
        seeds = load_seed_papers(ids, path.parent / "cache/seeds.json")
        for name, lines in groups.items():
            groups[name] = [
                seeds.get(re.sub(r"v\d+$", "", line), "") if ARXIV_ID_RE.match(line) else line
                for line in lines
            ]
            groups[name] = [line for line in groups[name] if line]
    return {name: lines for name, lines in groups.items() if lines}


def load_seed_papers(ids: list[str], cache_path: Path) -> dict[str, str]:
    """
    Get "title. abstract" of the seed papers from the arXiv abs pages, cached on disk
    so a flaky or rate-limited arXiv does not break the daily run.
    """
    from resources import fetch_abs_page

    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    ids = [re.sub(r"v\d+$", "", i) for i in ids]
    for arxiv_id in set(ids) - cache.keys():
        try:
            page = fetch_abs_page(arxiv_id)
            cache[arxiv_id] = f"{page['title']}. {page['abstract']}"
        except Exception as e:
            logger.warning(f"Failed to fetch seed paper {arxiv_id}: {e!r}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    logger.info(f"Loaded {sum(i in cache for i in ids)}/{len(ids)} seed papers.")
    return cache


def load_encoder(model: str) -> SentenceTransformer:
    """Load the embedding model on GPU, falling back to CPU if the GPU is unavailable or full."""
    kwargs = {"model_kwargs": {"torch_dtype": "auto"}}
    if torch.cuda.is_available():
        try:
            return SentenceTransformer(model, device="cuda", **kwargs)
        except torch.cuda.OutOfMemoryError:
            logger.warning("GPU out of memory, falling back to CPU.")
            torch.cuda.empty_cache()
    return SentenceTransformer(model, device="cpu", **kwargs)


def rerank_paper(
    candidate: list[ArxivPaper],
    interests: dict[str, list[str]],
    model: str = "Qwen/Qwen3-Embedding-0.6B",
) -> list[ArxivPaper]:
    """Score each candidate by its best match among the interests, highest first."""
    encoder = load_encoder(model)
    names = [name for name, lines in interests.items() for _ in lines]
    interest_feature = encoder.encode(
        [line for lines in interests.values() for line in lines], prompt=INTEREST_PROMPT
    )
    candidate_feature = encoder.encode(
        [f"{paper.title}. {paper.summary}" for paper in candidate],
        batch_size=16,
        show_progress_bar=sys.stderr.isatty(),
    )
    sim = encoder.similarity(candidate_feature, interest_feature)  # [n_candidate, n_interest]
    scores, best = sim.max(dim=1)
    for s, b, c in zip(scores, best, candidate):
        c.score = s.item()
        c.interest = names[b.item()]
    del encoder
    torch.cuda.empty_cache()
    return sorted(candidate, key=lambda x: x.score, reverse=True)


if __name__ == "__main__":
    print(load_interests("interests.txt"))
